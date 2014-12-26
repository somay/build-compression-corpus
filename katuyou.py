import sys, re, pickle
from collections import defaultdict

def parse(lines):
    result = [['']]
    
    for line in lines:
        line = re.sub(r';.*', '', line)
        if re.match(r'\((\S+)', line):
            result.append([''])
            continue
        m = re.search(r'\s*\(?\(\S+\s+(.+?)\s*\)', line)
        if m:
            result[-1].append(re.split(r'\s+', m.group(1)))
    return result
    
if __name__ == '__main__':
    file = '/home/somay/Downloads/juman-7.0/dic/JUMAN.katuyou'
    with open(file) as f:
        string = f.readlines()
    result = parse(string)

    
    # for i, t in enumerate(result):
    #     print('###', i)
    #     for j, form in enumerate(t):
    #         if form != None:
    #             print('', j, form, sep='\t')

    with open('katuyou.pickle', 'wb') as f:
        pickle.dump(result, f)
