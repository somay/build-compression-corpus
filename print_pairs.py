#!/usr/bin/python3
from subprocess import Popen, PIPE
import sys, re, functools, itertools, unittest, pickle
import xml.etree.ElementTree as ET
from collections import defaultdict
from knp2json import analyze_knp, show_analyzed_knp_info
from knp import decode_juman_info, preprocess_sentence, read_to_EOS

class BadPairException(Exception):
    pass

juman = Popen("juman", stdin=PIPE, stdout=PIPE, universal_newlines=True)
knp = Popen(("knp", "-dpnd-fast", "-tab"), stdin=PIPE, stdout=PIPE, universal_newlines=True)
with open('katuyou.pickle', 'rb') as f:
    inflection_table = pickle.load(f)

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

def is_no_predicates(basic_ids, basics):
    for i in basic_ids:
        if basics[i]['features']['用言']:
            return False
    return True

# 連結で
# 述語で終わっている
# 最小の木
def get_minimal_basic_tree(basics, morphemes, oc_indices):
    necessary_basic_ids = set()
    for i in range(len(basics)):
        for j in basics[i]['morphemes']:
            if j in oc_indices:
                necessary_basic_ids.add(i)

    # if is_no_predicates:
    #     raise BadPairException

    dependency_paths = []
    cooccurence = defaultdict(set)
    for i in necessary_basic_ids:
        path = {i}  # path from phrase[i] to the root of phrase tree
        while i != -1:
            # if basics[i]['relationType'] in ['A']:
            #     i = basics[i]['relation']
            #     continue
            path.add(i)

            # 「する」「なる」の場合には、格を含める
            if morphemes[basics[i]['morphemes'][0]][2] in ['する', 'なる']:
                for case in ['ト', 'ニ', 'カラ']:
                    try:
                        cooccurence[i].add(basics[i]['caseAnalysis'][case][-1]['#basics'])
                    except KeyError:
                        pass

            # 用言の主語を必ず短縮文に含める
            try:
                cooccurence[i].add(basics[i]['caseAnalysis']['ガ'][-1]['#basics'])
            except KeyError:
                pass

            # 並列関係にある基本句の一方をとばす
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

    for i in compressed_basic_ids:
        for j in cooccurence[i]:
            compressed_basic_ids.append(j)


    return compressed_basic_ids

# 後ろの助詞を取ってくる（活用も変える）
# 「行う」「開く」を「で」におきかえる

def compress_sentence(knp_info, title_mrphs, oc_pairs):
    ocs_in_title, ocs_in_sent = list(zip(*oc_pairs))
    phrases, basics, morphemes = knp_info['phrases'], knp_info['basics'], knp_info['morphemes']

    compressed_basic_ids = get_minimal_basic_tree(basics, morphemes, ocs_in_sent)

    compressed_phrase_ids = set()
    for i in range(len(phrases)):
        for j in phrases[i]['basics']:
            if j in compressed_basic_ids:
                compressed_phrase_ids.add(i)
    compressed_phrase_ids = list(sorted(compressed_phrase_ids))
    
    # if 文のopen classの並びにおいて隣り合うopen classがタイトルにおいても隣り合っている
    # and タイトルにおいて、隣り合うopen classの間に助詞がある
    # then 文中のopen classの間の形態素をその助詞に置き換える
    for i,j in oc_pairs:
        if i+2 < len(title_mrphs) and title_mrphs[i+1][3] == '助詞' and i+2 in ocs_in_title:
            ks = [k for k in sorted(ocs_in_sent) if k > j]
            if ks and morphemes[ks[0]][2] == title_mrphs[i+2][2]:
                # 構文木上でつながっていないフレーズをタイトルの助詞で置き換えない
                k, dst = morphemes[i][13], morphemes[ks[0]][13]
                is_linked = False
                while True:
                    if k == dst:
                        is_linked = True
                        break
                    elif k == -1:
                        is_linked = False
                        break
                    k = phrases[k]['relation']
                    
                # タイトルの助詞で置き換えてたいして文字数が減らない場合は置き換えない
                if is_linked and j + 2 != ks[0]:
                    for im in range(j+1, ks[0]):
                        morphemes[im][0] = ""
                    morphemes[j+1][0] = title_mrphs[i+1][0]

    compressed_mrph_ids = []
    for i in compressed_phrase_ids:
        j = phrases[i]['relation']
        if phrases[i]['relationType'] == 'P' and not j in compressed_phrase_ids:
            pi, pj = '', ''
            for ib in phrases[i]['basics']:
                for im in basics[ib]['morphemes']:
                    pi += morphemes[im][0]
            for ib in phrases[j]['basics']:
                for im in basics[ib]['morphemes']:
                    pj += morphemes[im][0]            
            print('#### relationType is P ####', pi, pj)
            # 並列している後の助詞を取ってくる
            if phrases[i]['features']['用言'] in ['動', '形']:
                # 対応している用言を見つける
                try:
                    infl1 = next(k for k in reversed(phrases[i]['morphemes']) if morphemes[k][12]['活用語'])
                    infl2 = next(k for k in reversed(phrases[j]['morphemes']) if morphemes[k][12]['活用語'])
                    for frm in inflection_table[morphemes[infl1][8]][morphemes[infl1][10]]:
                        for to in inflection_table[morphemes[infl1][8]][morphemes[infl2][10]]:
                            if frm == '*' and to == '*':
                                pass
                            elif frm == '*':
                                morphemes[infl1][0] += to
                            elif to == '*':
                                morphemes[infl1][0] = morphemes[infl1][0].replace(frm, '')
                            else:
                                morphemes[infl1][0] = morphemes[infl1][0].replace(frm, to)

                    former = list(filter(lambda l: l <= infl1, phrases[i]['morphemes']))
                    latter = list(filter(lambda l: l >  infl2, phrases[j]['morphemes']))
                    compressed_mrph_ids += former + latter
                except StopIteration:
                    pass
            else:
                ims = phrases[i]['morphemes'][:]
                while morphemes[ims[-1]][3] in ['助詞', '接尾辞', '特殊']:
                    ims.pop(-1)
                compressed_mrph_ids += ims
                rest = []
                for k in reversed(phrases[j]['morphemes']):
                    if morphemes[k][3] in ['助詞', '接尾辞', '特殊']:
                        rest.append(k)
                    else:
                        break
                compressed_mrph_ids += list(reversed(rest))
                    
        else:
            compressed_mrph_ids += phrases[i]['morphemes']

    while morphemes[compressed_mrph_ids[-1]][3] in ['助詞', '特殊']:
        compressed_mrph_ids.pop(-1)

    compressed = ""
    alignment = []
    count = 0
    for i in compressed_mrph_ids:
        if not (morphemes[i][0] == '「' or morphemes[i][0] == '」'):
            compressed += morphemes[i][0]
            alignment.append((i, count))
            count += 1
    return compressed, alignment


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
        
        if len(title_morphemes) <= 6:
            return

        open_classes = extract_open_classes(title_morphemes)
        # TODO: 単語の順序も考える
        if len(open_classes) >= 4 and set(open_classes).issubset(set(sent_words)):
            knp.stdin.write(sent_juman_output)
            sent_knp_output = read_to_EOS(knp.stdout)
            knp_info = analyze_knp(sent_knp_output)
            oc_pairs = mark_words_in_sent(knp_info['morphemes'], title_morphemes, open_classes)
            # show_analyzed_knp_info(knp_info)
            try:
                compressed, alignment = compress_sentence(knp_info, title_morphemes, oc_pairs)
            except BadPairException:
                return
            return compressed, alignment
        else:
            titles = titles[:-1]


if __name__ == '__main__':
    for hline, sent in yield_headline_and_1st_sent(sys.argv[1]):
        # hline = "李・韓国大統領:朝鮮半島平和「成し遂げる」"
        # sent = " 【ソウル西脇真一】韓国の李明博(イミョンバク)大統領は1日付で「新年の辞」を発表、11年には「必ず朝鮮半島の平和を成し遂げ、経済も継続して成長させていくことができると確信する」と強調した。"

        # hline = "水泳:世界選手権 シンクロ代表に足立ら11人"
        # sent =" 日本水泳連盟は5日、東京都内で選手選考委員会を開き、今年7月の世界選手権(上海)シンクロナイズドスイミング代表に、ソロの足立夢実(東京シンクロク)ら11人を選んだ。"
        # hline = "秋葉・広島市長:4選不出馬 ヒロシマに驚き 戸惑う五輪招致関係者 【大阪】"
        # sent = " 平和都市・ヒロシマの顔として、核兵器廃絶運動に精力的に取り組んできた秋葉忠利・広島市長(68)が、次期市長選への不出馬を表明した4日、被爆者や平和団体から驚きの声が上がった。"

        # hline = "北朝鮮:韓国に「無条件対話を」"
        # sent=" 【平壌・共同】北朝鮮は5日、朝鮮中央通信を通じ、韓国に無条件の当局間対話開催を提案するなど4項目からなる政府、政党、団体の「連合声明」を発表した。"

        # hline = "生物多様性保全:企業の75%「取り組んでない」--環境省調査"
        # sent = " 国内企業を対象とした環境省のアンケートで、事業活動の中で生物多様性の保全に「取り組んでいない」と回答した企業が75%に上ることが分かった。"

        # hline = "オーロラ展:野口宇宙飛行士らが宇宙で撮影 東京・新宿で5日から"
        # sent = " 野口聡一宇宙飛行士(45)らが国際宇宙ステーションから撮影したオーロラの写真を中心とした「宇宙から見たオーロラ展2011」が5~31日、東京都新宿区新宿3のコニカミノルタプラザ(03・3225・5001)で開かれる。"
        compressed_alignment = grammarize_headline(hline, sent[1:])
        if compressed_alignment:
            compressed, alignment = compressed_alignment
            print(hline)
            print(sent)
            print(compressed)
            for i, j in alignment:
                print(str(i) + '-' + str(j), end=' ')
            print('\n')
            # sys.stdin.readline()
    knp.terminate()
    juman.terminate()
    sys.exit(0)
