import re
from knp.knp2json import analyze_case_analysis

def decode_juman_info(juman_output):
    result = []
    for line in juman_output.split('\n'):
        if line != 'EOS' and line != '' and line[0] != '@':
            morpheme = line.split(' ', 11)
            result.append(morpheme)
    return result
        
# TODO: 共通化できそう
del_regex = re.compile(r'^◇|(?:\(.*?\)|【.*?】)|=[^。]*?=')
sub_regex = re.compile(r'=写真[^=、。]*?([、。])|=写真、[^=。]*?(?:撮影|提供)([、。])')
transtable = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZabdcefghijklmnopqrstuvwxyz0123456789 ()~=*+[{|}>,<];!:?&%"-/',
                           'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ０１２３４５６７８９　（）〜＝＊＋［｛｜｝〉，〈］；！：？＆％、ー／')

def preprocess_sentence(sent):
    sent = re.sub(del_regex, '', sent)
    sent = re.sub(sub_regex, r'\1', sent)
    sent = sent.translate(transtable)
    return sent

def read_until_EOS(stream):
    output = ""
    while True:
        line = stream.readline()
        output += line
        if line == 'EOS\n':
            break
    return output

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

def decode_features(feature_strs):
    fs = features()
    for f in feature_strs:
        splitted = f.split(':', maxsplit=1)
        if len(splitted) > 1:
            if splitted[0] == '格解析結果':
                fs['格解析結果'] = analyze_case_analysis(splitted[1].split(':', 2)[-1])
            else:
                fs[splitted[0]] = splitted[1]
        else:
            fs[splitted[0]] = True
    return fs

class JUMANInfo():
    def __init__(self, juman_output):
        self.mrphs = []
        for line in juman_output.split('\n'):
            if line != 'EOS' and line != '' and line[0] != '@':
                m = Morpheme(line)
                self.mrphs.append(m)

    def __getitem__(self, idx):
        return self.mrphs[idx]
    
    def __len__(self):
        return len(self.mrphs)

    def __str__(self):
        string = ''
        for i, m in enumerate(self.mrphs):
            string += str(i) + '\t' + str(m) + '\n'
        return string

class KNPInfo():
    def __init__(self, string):
        self.phrases = []
        self.basics = []
        self.mrphs = []
        
        for l in string.split('\n'):
            if len(l) < 1 or l[0] in "#E":
                continue

            if l[0] == '*':
                p = Phrase(l)
                self.phrases.append(p)

            elif l[0] == '+':
                b = Basic(l)
                b.phrase = len(self.phrases) - 1
                self.basics.append(b)
                self.phrases[-1].basics.append(len(self.basics)-1)
            else:
                m = Morpheme(l)
                m.basic = len(self.basics) - 1
                self.mrphs.append(m)
                self.basics[-1].mrphs.append(len(self.mrphs)-1)
    
    def parent_of_mrph(self, i):
        if self.basics[self.mrphs[i].basic].mrphs[-1] == i:
            return None
        else:
            return self.mrphs[i+1]
    
    def __str__(self):
        string = ''
            
        for i, p in enumerate(self.phrases):
            string += str(i) + '\t' + str(p) + '\n'
        string += '\n'
        
        for i, b in enumerate(self.basics):
            string += str(i) + '\t' + str(b) + '\n'
        string += '\n'

        for i, m in enumerate(self.mrphs):
            string += str(i) + '\t' + str(m) + '\n'

        return string

class Phrase():
    def __init__(self, linestr):
        self.basics = []
        
        f = re.split('>?<?', linestr)
        self.rel = int(f[0][2:-2])
        self.reltype = f[0][-2]   
        self.features = decode_features(f[1:-1])  # 最初は係り受けの情報、最後は空
    
    def __str__(self):
        return ' '.join([str(self.rel) + self.reltype,\
                          str(self.basics), str(self.features)])
class Basic():
    def __init__(self, linestr):
        self.phrase = -1
        self.mrphs = []

        f = re.split('>?<?', linestr)
        self.rel = int(f[0][2:-2])
        self.reltype = f[0][-2]        
        self.features = decode_features(f[1:-1])

    def type(self):
        typ = self.features['体言']
        if not typ:
            typ = self.features['用言']
        if not typ:
            typ = None
        return typ

    def __str__(self):
        return ' '.join([str(self.rel) + self.reltype,\
                          str(self.phrase), str(self.mrphs), str(self.features)])
class Morpheme():
    def __init__(self, linestr):
        self.basic = -1
        
        f = re.split('>?<?', linestr)
        s = f[0].split(' ', 11)

        self.input = s[0]
        self.pron = s[1]
        self.orgn = s[2]
        self.pos = s[3]
        self.__posid = int(s[4])
        self.subpos = s[5]
        self.__subposid = int(s[6])
        self.inftype = s[7]
        self.inftypeid = int(s[8])
        self.inf = s[9]
        self.infid = int(s[10])
        self.features = decode_features(f[1:-1])
    
    def posid(self):
        return self.__posid * 10000 + self.__subposid

    def __str__(self):
        l = [self.input, self.pron, self.orgn, self.pos, self.subpos,\
             self.inftype, self.inf, str(self.features)]
        return ' '.join(l)
