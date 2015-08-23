## What's this

日本語の文短縮の教師データを作るスクリプトです。
アルゴリズムはOvercoming the Lack of Parallel Data in Sentence Compression (Filippova & Altun, 2013)に拠っています。
このアルゴリズムはニュース記事などのタイトルと本文の一文目はだいたい似た意味であることが少なからずあるという事実を利用しています。
人手で（自分で）評価したところ、教師データの正確さは8割～9割くらいでした。

日本語形態素解析器JUMANと日本語係り受け解析器KNPに依存しています。
mecabやCaboChaよりかなり遅いですが動詞の主語がなんであるかなどの情報が必要だったのでそれらは使えませんでした。
速度の問題を改善するためにKNPに-dpnd-fastオプションをつけています。

## Usage

./print_pairs.py xml-file-like-毎日新聞コーパス > file-to-store-pairs.txt

第一引数のコーパスは以下の様なフォーマットで与えてください。
これは毎日新聞コーパス（http://www.nichigai.co.jp/sales/corpus.html）とほとんど同じ形式です
（<DATA>要素を根に持つようにしている点が違う）。

'''xml
<DATA>
  <DOC>
    <ID>00000010</ID>
    <DATE>2011-01-01</DATE>
    <EDITION>M</EDITION>
    <SECTION>1</SECTION>
    <PAGE>1</PAGE>
    <IMAGE>N</IMAGE>
    <RIGHTS>有</RIGHTS>
    <TITLE><![CDATA[記事タイトル（必須）]]></TITLE>
    <TEXT><![CDATA[記事本文（必須）]]></TEXT>
  </DOC>
  <DOC>
  ... (以下同様)
</DATA>
'''

結果は標準出力に以下のようなフォーマットで出力されます。

> 元の記事タイトル
> 記事本文の一文目（短縮前の文）
> 短縮文
> 21-0 22-1 23-2 24-3 28-4 29-5 30-6 31-7 32-8 33-9 34-10 35-11 40-12 41-13 42-14 43-15 44-16 45-17 46-18 （元の文と短縮文の間の形態素の対応関係））
> 
> 元の記事タイトル
> ... （以下同様）
