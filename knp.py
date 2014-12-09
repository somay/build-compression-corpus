#!/usr/bin/python3
from subprocess import Popen, PIPE
import sys, re, functools, itertools, unittest
import xml.etree.ElementTree as ET
from knp2json import analyze_knp, show_analyzed_knp_info

juman = Popen("juman", stdin=PIPE, stdout=PIPE, universal_newlines=True)
knp = Popen(("knp", "-ne", "-tab"), stdin=PIPE, stdout=PIPE, universal_newlines=True)

def yield_headline_and_1st_sent(filename):
    title, text = '', ''
    pattern = re.compile(r'([^。「」]*?「.*?」)*[^。「」]*?。') #日本語の1文にマッチする正規表現
    
    for event, elem in ET.iterparse(filename):
        if elem.tag == 'TITLE':
            title = elem.text
        elif elem.tag == 'TEXT':
            if title and elem.text:
                # elem.textから最初の文を抜き出す
                for line in elem.text.split('\n'):
                    matchobj = pattern.search(line)
                    if matchobj:
                        text = matchobj.group(0)
                        break
                if title and text:
                    yield title, text
            title, text = '', ''
        elif elem.tag == 'DOC':
            continue
        elem.clear()

def decode_juman_info(juman_output):
    result = []
    for line in juman_output.split('\n'):
        if line != 'EOS' and line != '' and line[0] != '@':
            morpheme = line.split(' ', 11)
            result.append(morpheme)
    return result
        
# TODO: 共通化できそう
del_regex = re.compile(r'^◇|(?:\(.*?\)|【.*?】)|=写真[^、。]*?=|=写真、[^=。]*?(?:撮影|提供)=')
sub_regex = re.compile(r'=写真[^=、。]*?([、。])|=写真、[^=。]*?(?:撮影|提供)([、。])')
transtable = str.maketrans('1234567890 ()~=*+[{|}>,<];!:?&%"-/',
                           '１２３４５６７８９０　（）〜＝＊＋［｛｜｝〉，〈］；！：？＆％、ー／')

def preprocess_sentence(sent):
    sent = re.sub(del_regex, '', sent)
    sent = re.sub(sub_regex, r'\1', sent)
    sent = sent.translate(transtable)
    return sent

def read_to_EOS(stream):
    output = ""
    while True:
        line = stream.readline()
        output += line
        if line == 'EOS\n':
            break
    return output

def is_open_class(mrph):
    return mrph[3] in ['名詞', '形容詞', '副詞', '動詞'] or \
          (mrph[3] == '未定義語' and len(mrph[0]) >= 2)

# headlineから名詞、動詞、副詞、形容詞のリストを取り出す。
def extract_open_classes(morphemes):
    return [m[2] for m in morphemes if is_open_class(m)]


def first_open_class(mrphs):
    for m in mrphs:
        if is_open_class(m):
            return m
    return None

def mark_words_in_sent(sent_mrphs, title_mrphs, open_classes):
    marked_mrphs = []
    open_class_dict = {}
    # is_plural = False
    for oc in set(open_classes):
        its = list(filter(lambda i: title_mrphs[i][2] == oc, range(len(title_mrphs))))
        iss = list(filter(lambda i: sent_mrphs[i][2] == oc, range(len(sent_mrphs))))
        open_class_dict[oc] = (its, iss)
        # if len(iss) > len(its):
        #     is_plural = True

    # titleに現れる回数だけsent内にmarkをつける
    for oc in open_class_dict:
        its, iss = open_class_dict[oc]

        # 各open classの出現iに対してscoreをつけて、scoreの高いlen(its)個をmark
        scores = dict(((i,j),0) for i in its for j in iss)
    
        for i, j in scores.keys():

            # 周辺の形態素の一致によるscore付け
            identity_count = 0
            for o in range(-2, 3):
                io, jo = i + o, j + o
                if io < 0 or io >= len(title_mrphs) or \
                   jo < 0 or jo >= len(sent_mrphs):
                    continue
                if title_mrphs[io][2] == sent_mrphs[jo][2]:
                    identity_count += 1 if title_mrphs[io][2] != '、' else 0.1
                else:
                    identity_count = 0
                scores[(i,j)] = max(scores[(i,j)], identity_count - 1)

             # 周辺のopen classの一致によるscore付け
            oc_score = 0
            len_sent = len(sent_mrphs)

            # 一つ後のopen class
            itss = sorted(k for ks, _ in open_class_dict.values() for k in ks)
            isss = sorted(k for _, ks in open_class_dict.values() for k in ks)
            next_it = [k for k in itss if k > i]
            next_is = [k for k in isss if k > j]
            next_tm = title_mrphs[next_it[0]][2] if next_it else None
            next_sm = sent_mrphs[next_is[0]][2] if next_is else None
            if next_tm == next_sm:   # open class間の距離によって点数を変える
                penalty = (next_is[0] - j if next_is else len_sent - j) / len_sent
                oc_score += 1 - penalty

            # 一つ前のopen class
            prev_it = [k for k in reversed(itss) if k < i]
            prev_is = [k for k in reversed(isss) if k < j]
            prev_tm = title_mrphs[prev_it[0]][2] if prev_it else None
            prev_sm = sent_mrphs[prev_is[0]][2] if prev_is else None
            if prev_tm == prev_sm:   # open class間の距離によって点数を変える
                penalty = (j - (prev_is[0] if prev_is else 0)) / len_sent
                oc_score += 1 - penalty

            scores[(i,j)] += oc_score

        # sent = [m[0] for m in sent_mrphs]

        # scoreの高いi,jのペアから順にmarkしていく
        # 既にi, jのどちらかがmarked_mrphsに含まれているペアは新たに追加しない
        for i,j in sorted(scores.keys(), key=lambda p: scores[p], reverse=True):
            if (not i in map(lambda p:p[0], marked_mrphs)) and \
               (not j in map(lambda p:p[1], marked_mrphs)):
                marked_mrphs.append((i,j))

    # if is_plural:
    #     for i,j in marked_mrphs:
    #         print(sent[j-1 if j > 0 else 0:j+2], end=', ')
    #         print(sent_mrphs[j][2])
    #     print(''.join(m[0] for m in sent_mrphs))
    #     print(''.join(m[0] for m in title_mrphs))

    return marked_mrphs

# 連結で
# 述語で終わっている
# 最小の木
def get_minimal_basic_tree(basics, morphemes, oc_indices):
    necessary_basic_ids = set()
    for i in range(len(basics)):
        for j in basics[i]['morphemes']:
            if j in oc_indices:
                necessary_basic_ids.add(i)

    dependency_paths = []
    for i in necessary_basic_ids:
        path = {i}  # path from phrase[i] to the root of phrase tree
        while i != -1:
            if basics[i]['relationType'] in ['A']:
                i = basics[i]['relation']
                continue
            path.add(i)
            try:                            # 用言の主語を必ず短縮文に含める
                path.add(basics[i]['caseAnalysis']['ガ'][-1]['#basics'])
            except:
                pass
            if basics[i]['relationType'] == 'P':
                i = basics[i]['relation']
            i = basics[i]['relation']
        dependency_paths.append(path)

    intersection = functools.reduce(lambda a, b: a.intersection(b), dependency_paths)
    union = functools.reduce(lambda a, b: a.union(b), dependency_paths)
    complement = set(range(len(basics))) - union

    for i in sorted(intersection):
        intersection.remove(i)
        if basics[i]['features']['用言']: # phrase[i] is the new root of compressed sentence
            break

    compressed_basic_ids = list(range(len(basics)))
    for i in intersection.union(complement):
        compressed_basic_ids.remove(i)

    return compressed_basic_ids

def compress_sentence(knp_info, title_mrphs, oc_pairs):
    ocs_in_title, ocs_in_sent = list(zip(*oc_pairs))
    basics, morphemes = knp_info['basics'], knp_info['morphemes']

    compressed_basic_ids = get_minimal_basic_tree(basics, morphemes, ocs_in_sent)

    # if 文のopen classの並びにおいて隣り合うopen classがタイトルにおいても隣り合っている
    # and タイトルにおいて、隣り合うopen classの間に助詞がある
    # then 文中のopen classの間の形態素をその助詞に置き換える
    # print(open_classes)
    for i,j in oc_pairs:
        if i+2 < len(title_mrphs) and title_mrphs[i+1][3] == '助詞' and i+2 in ocs_in_title:
            ks = [k for k in sorted(ocs_in_sent) if k > j]
            if ks and morphemes[ks[0]][2] == title_mrphs[i+2][2]:
                for im in range(j+1, ks[0]):
                    morphemes[im][0] = ""
                morphemes[j+1][0] = title_mrphs[i+1][0]

    compressed_mrph_ids = []
    for i in compressed_basic_ids:
        for j in basics[i]['morphemes']:
            compressed_mrph_ids.append(j)
            
    for i in reversed(compressed_mrph_ids):
        if not (morphemes[i][3] in ['助詞', '特殊']):
            break
        morphemes[i][0] = ""

    compressed = ""
    for i in compressed_mrph_ids:
        if not (morphemes[i][0] == '「' or morphemes[i][0] == '」'):
            compressed += morphemes[i][0]
    return compressed


def grammarize_headline(headline, sent):
    juman.stdin.write(preprocess_sentence(sent) + '\n')
    sent_juman_output = read_to_EOS(juman.stdout)
    sent_morphemes = decode_juman_info(sent_juman_output)

    sent_words = extract_open_classes(sent_morphemes)

    headline = preprocess_sentence(headline)
    titles = [s for t in headline.split('　') for s in t.split('ーー')]
    while titles:
        title = '　'.join(titles) + '\n'
        juman.stdin.write(preprocess_sentence(title))
        title_juman_output = read_to_EOS(juman.stdout)
        title_morphemes = decode_juman_info(title_juman_output)
        
        open_classes = extract_open_classes(title_morphemes)

        # TODO: 単語の順序も考える
        if len(open_classes) >= 4 and set(open_classes).issubset(set(sent_words)):
            knp.stdin.write(sent_juman_output)
            sent_knp_output = read_to_EOS(knp.stdout)
            knp_info = analyze_knp(sent_knp_output)
            oc_pairs = mark_words_in_sent(knp_info['morphemes'], title_morphemes, open_classes)
            # show_analyzed_knp_info(knp_info)
            compressed = compress_sentence(knp_info, title_morphemes, oc_pairs)
            return compressed
        else:
            titles = titles[:-1]


if __name__ == '__main__':
    for hline, sent in yield_headline_and_1st_sent(sys.argv[1]):
        # hline = "オーロラ展:野口宇宙飛行士らが宇宙で撮影 東京・新宿で5日から"
        # sent = " 野口聡一宇宙飛行士(45)らが国際宇宙ステーションから撮影したオーロラの写真を中心とした「宇宙から見たオーロラ展2011」が5~31日、東京都新宿区新宿3のコニカミノルタプラザ(03・3225・5001)で開かれる。"
        compressed = grammarize_headline(hline, sent[1:])
        if compressed:
            print(hline)
            print(sent)
            print(compressed)
            print()
        #     sys.stdin.readline()
    knp.terminate()
    juman.terminate()
    sys.exit(0)
