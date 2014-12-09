#!/usr/bin/python3
from subprocess import Popen, PIPE
import sys, re, functools
from newspapers import yield_headline_and_1st_sent
from knp2json import analyze_knp, show_analyzed_knp_info

juman = Popen("juman", stdin=PIPE, stdout=PIPE, universal_newlines=True)
knp = Popen(("knp", "-ne", "-tab"), stdin=PIPE, stdout=PIPE, universal_newlines=True)

def decode_juman_info(juman_output):
    result = []
    for line in juman_output.split('\n'):
        if line != 'EOS' and line != '':
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

# headlineから名詞、動詞、副詞、形容詞のリストを取り出す。
def extract_open_classes(morphemes):
    return [m[2] for m in morphemes if m[3] in ['名詞', '形容詞', '副詞', '動詞'] or \
                                      (m[3] == '未定義語' and len(m[0]) >= 2)]

def mark_words_in_sent(sent_morphemes, title_morphemes, open_classes):
    for i in range(len(open_classes)):
        ls = list(filter(lambda j: sent_morphemes[j]['original'] == open_classes[i],
                        range(len(sent_morphemes))))
        lt = list(filter(lambda j: title_morphemes[j][3] == open_classes[i],
                         range(len(title_morphemes))))
        if len(ls) == 1:
            sent_morphemes[ls[0]]['marked'] = True
        elif len(ls) >= 2:
            was_marked = False
            if len(lt) == 1:
                for j in ls:
                    ms1 = ''.join(m['original'] for m in sent_morphemes[j:j+3])
                    ms2 = ''.join(m['original'] for m in sent_morphemes[j-1:j+2])
                    ms3 = ''.join(m['original'] for m in sent_morphemes[j-2:j+1])
                    lt[0] = k
                    mt1 = ''.join(m[3] for m in title_morphemes[k:k+3])
                    mt2 = ''.join(m[3] for m in title_morphemes[k-1:k+2])
                    mt3 = ''.join(m[3] for m in title_morphemes[k-2:k+1])
                    pred = lambda x,y: x and y and x == y
                    if pred(ms1, mt1) or pred(ms2, mt2) or pred(ms3, mt3):
                        sent_morphemes[j]['marked'] = True
                        was_marked = True
                        break

                    try:
                        prev_oc = next(m['original'] for m in reversed(sent_morphemes[:j])
                                       if m['original'] in open_classes)
                    except StopIteration:
                        prev_oc = None
                    try:
                        next_oc = next(m['original'] for m in sent_morphemes[j+1:]
                                       if m['original'] in open_classes)
                    except StopIteration:
                        next_oc = None
                    if (prev_oc and prev_oc == open_classes[i-1]) and (next_oc and next_oc == open_classes[i+1]):
                        sent_morphemes[j]['marked'] = True
                        was_marked = True
                        break
                else:
                    print("mark_words_in_sent", file=sys.stderr)
            if not was_marked:
                    print("mark_words_in_sent: 0 mark", open_classes[i], file=sys.stderr)

    return sent_morphemes
                    
        

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
    print(open_classes)
    for i in range(len(title_morphemes) - 2):
        curr_mrph = title_morphemes[i][2]
        if curr_mrph in open_classes:
            next_mrph = title_morphemes[i + 2][2]
            print(curr_mrph, next_mrph)
            if title_morphemes[i + 1][3] == '助詞' and next_mrph in open_classes:
                j = [m['original'] for m in morphemes].index(curr_mrph)
                k = next(i for i in range(j+1, len(morphemes)) if morphemes[i]['original'] in open_classes)
                print(j, k)
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
        hline = "オーロラ展:野口宇宙飛行士らが宇宙で撮影 東京・新宿で5日から"
        sent = " 野口聡一宇宙飛行士(45)らが国際宇宙ステーションから撮影したオーロラの写真を中心とした「宇宙から見たオーロラ展2011」が5~31日、東京都新宿区新宿3のコニカミノルタプラザ(03・3225・5001)で開かれる。"
        compressed = grammarize_headline(hline, sent[1:])
        if compressed:
            print(hline)
            print(sent)
            print(compressed)
            print()
            sys.stdin.readline()
    knp.terminate()
    juman.terminate()
    sys.exit(0)
