#!/usr/bin/python3
# using https://github.com/nkmry/knp2json for reference

import re

class features(dict):
    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            return False
    
    def __str__(self):
        l = []
        for key in self:
            if self[key] == True:
                l.append(str(key))
            else:
                l.append("{0}: {1}".format(key, self[key]))
        return '{' + ', '.join(l) + '}'

    @staticmethod
    def normalized_representative(string):
        return re.sub(r'(/.*?\+|/.*$)', '', string)


def analyze_knp(knp_tab_output):
    # phrase = {type, relation, relationType, basics, morphemes, features}
    # basic = {type, relation, relationType, phrase, features [, case, caseAnalysis]}
    # morpheme = {type, phrase, morpheme, features}
    lines = knp_tab_output.split('\n')
    phrases = []
    basics = []
    morphemes = []
    for l in lines:
        if len(l) < 1 or l[0] in "#E":
            continue
        d = {}
        f = re.split('>?<?', l)
        if l[0] == '*':
            d['features'] = decode_features(f[1:-1], d)  # 最初は係り受けの情報、最後は空
            d['relation'] = int(f[0][2:-2])
            d['relationType'] = f[0][-2]
            d['basics'] = []
            d['morphemes'] = []
            phrases.append(d)
        elif l[0] == '+':
            d['phrase'] = len(phrases) - 1
            d['morphemes'] = []
            d.update(analyze_basic(f[:-1]))
            basics.append(d)
            phrases[-1]['basics'].append(len(basics)-1)
        else:
            # d['phrase'] = len(phrases) - 1
            m = analyze_morpheme(f[:-1])
            m.append(len(phrases) - 1)
            morphemes.append(m)
            phrases[-1]['morphemes'].append(len(morphemes)-1)
            basics[-1]['morphemes'].append(len(morphemes)-1)
    return {"phrases": phrases, "basics": basics, "morphemes": morphemes}

def decode_features(feature_str, d):
    fs = features()
    for f in feature_str:
        splitted = f.split(':', maxsplit=1)
        if len(splitted) > 1:
            if splitted[0] == "解析格":   # Basic
                d['case'] = splitted[1]
            elif splitted[0] == "格解析結果":   # Basic
                d['caseAnalysis'] = analyze_case_analysis(splitted[1].split(':', 2)[-1])
            elif splitted[0] == 'Wikipediaエントリ':   # Basic, Morpheme
                d['wikipedia'] = splitted[1]
            else:
                fs[splitted[0]] = splitted[1]
        else:
            fs[splitted[0]] = True
    return fs
    
def analyze_basic(basic_info):
    d = {'relation': int(basic_info[0][2:-2]), 'relationType': basic_info[0][-2]}
    d['features'] = decode_features(basic_info[1:], d)
    return d


def analyze_case_analysis(case_analysis_string):
    elements = case_analysis_string.split(';')
    d = {}
    for element in elements:
        if not 'U/-/-/-/-' in element:
            splitted = element.split('/')
            e = {'flag': splitted[1],
                 'expression': splitted[2],
                 '#basics': int(splitted[3]),
                 'sentenceId': int(splitted[5])}
            if d.get(splitted[0]):
                d[splitted[0]].append(e)
            else:
                d[splitted[0]] = [e]
    return d

def analyze_morpheme(morpheme_info):
    s = morpheme_info[0].split(' ', 11)
    s[4], s[6], s[8], s[10] = int(s[4]), int(s[6]), int(s[8]), int(s[10])
    d = {}
    s.append(decode_features(morpheme_info[1:], d))
    # d = {'input': s[0], 'pronunciation': s[1], 'original': s[2], 'pos': s[3], 'posId': s[4], 'subPos': s[5],
    #      'subPosId': s[6], 'inflectionType': s[7], 'inflectionTypeId': s[8], 'inflection': s[9], 'inflectionId': s[10],
    #      'others': s[11]}
    # d['features'] = decode_features(morpheme_info[1:], d)
    return s


def show_analyzed_knp_info(analyzed_knp_info):
    phrases = analyzed_knp_info["phrases"]
    basics = analyzed_knp_info["basics"]
    morphemes = analyzed_knp_info["morphemes"]
    print("### 文節 ###")
    attrs = ['relation', 'relationType', 'basics', 'morphemes', 'features', 'type']
    for i in range(len(phrases)):
        print(str(i) + ': ' + convert_dictionary_to_string(phrases[i], attrs))
    print("### 形態素 ###")
    attrs = ['phrase', 'input', 'pos', 'subPos', 'wikipedia', 'features', 'type']
    for i in range(len(morphemes)):
        print(str(i) + ': ' + convert_dictionary_to_string(morphemes[i], attrs))
    print("### 基本句 ###")
    attrs = ['relation', 'relationType', 'phrase', 'morphemes', 'case', 'caseAnalysis', 'features', 'type']
    for i in range(len(basics)):
        print(str(i) + ': ' + convert_dictionary_to_string(basics[i], attrs))


def convert_dictionary_to_string(dictionary, keys):
    s = '{'
    for k in keys:
        if k in dictionary.keys():
            s += '\'' + k + '\':' + str(dictionary[k]) + ', '
    s += '}'
    return s

