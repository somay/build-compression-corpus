#!/usr/bin/python3
from subprocess import Popen, PIPE
import sys, re, functools, unittest
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
    open_class_dict = {}
    for oc in set(open_classes):
        iss = list(filter(lambda i: sent_mrphs[i][2] == oc, range(len(sent_mrphs))))
        its = list(filter(lambda i: title_mrphs[i][2] == oc, range(len(title_mrphs))))
        open_class_dict[oc] = (iss, its)

    for oc in open_class_dict:
        iss, its = open_class_dict[oc]
        if len(iss) <= len(its):
            for i in iss:
                sent_mrphs[i][11] = True
        else:                             # titleに現れる回数だけsent内にmarkをつける
            # 各open classの出現iに対してscoreをつけて、scoreの高いlen(its)個をmark
            scores = dict((i,0) for i in iss)
            for i in its:
                for j in iss:
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
                        scores[j] = max(scores[j], identity_count - 1)

                    # 周辺のopen classの一致によるscore付け
                    identity_count = 0
                    itss = sorted(k for _, ks in open_class_dict.values() for k in ks)
                    isss = sorted(k for ks, _ in open_class_dict.values() for k in ks)
                    next_it = [k for k in itss if k > i]
                    next_is = [k for k in isss if k > j]
                    next_tm = title_mrphs[next_it[0]][2] if next_it else None
                    next_sm = sent_mrphs[next_is[0]][2] if next_is else None
                    if next_tm == next_sm:   # open class間の距離によって点数を変える
                        penalty = (next_is[0] - j if next_is else len(sent_mrphs) - j) / len(sent_mrphs)
                        identity_count += 1 - penalty
                    prev_it = [k for k in reversed(itss) if k < i]
                    prev_is = [k for k in reversed(isss) if k < j]
                    prev_tm = title_mrphs[prev_it[0]][2] if prev_it else None
                    prev_sm = sent_mrphs[prev_is[0]][2] if prev_is else None
                    if prev_tm == prev_sm:   # open class間の距離によって点数を変える
                        penalty = (j - (prev_is[0] if prev_is else 0)) / len(sent_mrphs)
                        identity_count += 1 - penalty
                    scores[j] += identity_count
            #         if title_mrphs[i][2] =='進退':
            #             print(next_tm, next_sm)
            #             print(extract_open_classes(title_mrphs))
            #             print(itss, isss)
            # print(scores)
            # score順にソートする
            marked_mrphs = sorted(iss, key=lambda i:scores[i], reverse=True)
            # マークをつける
            sent = [m[2] for m in sent_mrphs]
            for i in marked_mrphs[:len(its)]:
                sent_mrphs[i][11] = True
                # print(sent[i-1 if i >0 else 0:i+2], end=', ')
            # print(sent_mrphs[marked_mrphs[0]][2])
            # print(''.join(m[0] for m in sent_mrphs))
            # print(''.join(m[0] for m in title_mrphs))
# 連結で
# 述語で終わっている
# 最小の木
def compress_sentence(knp_info, title_morphemes, open_classes):
    sentence = []
    phrases, basics, morphemes = knp_info['phrases'], knp_info['basics'], knp_info['morphemes']
    necessary_phrase_ids = set()
    for i in range(len(phrases)):
        for j in phrases[i]['morphemes']:
            if morphemes[j]['original'] in open_classes:
                necessary_phrase_ids.add(i)

    dependency_paths = []
    for i in necessary_phrase_ids:
        path = set()                      # path from phrase[i] to the root of phrase tree
        while i != -1:
            path.add(i)
            while phrases[i]['relationType'] == 'P':
                i = phrases[i]['relation']
            i = phrases[i]['relation']
                
        dependency_paths.append(path)

    intersection = functools.reduce(lambda a, b: a.intersection(b), dependency_paths)
    union = functools.reduce(lambda a, b: a.union(b), dependency_paths)
    complement = set(range(len(phrases))) - union

    for i in sorted(intersection):
        intersection.remove(i)
        if phrases[i]['features']['用言']: # phrase[i] is the new root of compressed sentence
            break

    for i in intersection.union(complement):
        phrases[i] = None

    # if 文のopen classの並びにおいて隣り合うopen classがタイトルにおいても隣り合っている
    # and タイトルにおいて、隣り合うopen classの間に助詞がある
    # then 文中のopen classの間の形態素をその助詞に置き換える
    # print(open_classes)
    for i in range(len(title_morphemes) - 2):
        curr_mrph = title_morphemes[i][2]
        if curr_mrph in open_classes:
            next_mrph = title_morphemes[i + 2][2]
            print(curr_mrph, next_mrph)
            if title_morphemes[i + 1][3] == '助詞' and next_mrph in open_classes:
                j = [m['original'] for m in morphemes].index(curr_mrph)
                k = next(i for i in range(j+1, len(morphemes)) if morphemes[i]['original'] in open_classes)
                # print(j, k)
                if morphemes[k]['original'] == next_mrph:
                    for im in range(j+1, k):
                        morphemes[im]['input'] = ""
                    morphemes[j+1]['input'] = title_morphemes[i + 1][0]

    compressed = ""
    for p in phrases:
        if p:
            for i in p['morphemes']:
                compressed += morphemes[i]['input']
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
            mark_words_in_sent(sent_morphemes, title_morphemes, open_classes)
            return 
            knp.stdin.write(sent_juman_output)
            sent_knp_output = read_to_EOS(knp.stdout)
            knp_info = analyze_knp(sent_knp_output)
            # show_analyzed_knp_info(knp_info)
            compressed = compress_sentence(knp_info, title_morphemes, open_classes)
            return compressed
        else:
            titles = titles[:-1]


if __name__ == '__main__':
    for hline, sent in yield_headline_and_1st_sent(sys.argv[1]):
        # hline = "オーロラ展:野口宇宙飛行士らが宇宙で撮影 東京・新宿で5日から"
        # sent = " 野口聡一宇宙飛行士(45)らが国際宇宙ステーションから撮影したオーロラの写真を中心とした「宇宙から見たオーロラ展2011」が5~31日、東京都新宿区新宿3のコニカミノルタプラザ(03・3225・5001)で開かれる。"
        compressed = grammarize_headline(hline, sent[1:])
        # if compressed:
        #     print(hline)
        #     print(sent)
        #     print(compressed)
        #     print()
        #     sys.stdin.readline()
    knp.terminate()
    juman.terminate()
    sys.exit(0)
