"""Apply the manually checked 2026-10-20 source additions (idempotent)."""
import json
from pathlib import Path

DATA = Path(__file__).parent / 'docs/data_sox'

# id | announcement date | title | URL | market date when explicitly after close
ADDITIONS = '''fed-1995-feb|1995-02-01|FRBの利上げ（1995年2月）|https://www.federalreserve.gov/fomc/19950201default.htm|
fed-1995-jul|1995-07-06|FRBの利下げ（1995年7月）|https://www.federalreserve.gov/fomc/19950706default.htm|
pentiumii-1997|1997-05-07|Intel Pentium II発表|https://www.intel.com/pressroom/kits/quickrefyr.htm|
pentiumii-300|1997-08-18|Intel Pentium II 300MHz投入|https://www.intel.com/pressroom/kits/quickrefyr.htm|
nvda-2017q3|2017-11-09|NVIDIAの2018年度第3四半期決算|https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2018|2017-11-10
mu-2019q2|2019-03-20|Micronの2019年度第2四半期決算|https://investors.micron.com/news/press-release/2019/Micron-Technology-Inc--Reports-Results-for-the-Second-Quarter-of-Fiscal-2019-03-20-2019/default.aspx|2019-03-21
tsmc-2019q2|2019-07-18|TSMCの2019年第2四半期決算|https://www.sec.gov/Archives/edgar/data/1046179/000119312519195998/d779506d6k.htm|
ti-2019q2|2019-07-23|Texas Instrumentsの2019年第2四半期決算|https://www.ti.com/about-ti/newsroom/news-releases/2019/2019-07-23-ti-reports-second-quarter-2019-financial-results-and-shareholder-returns.html|2019-07-24
china-tariff-2019sep|2019-09-11|中国の対米関税除外措置と通商協議期待|https://www.investing.com/news/stock-market-news/futures-flat-as-trade-moves-offer-mixed-signals-1975376|
intel-2019q3|2019-10-24|Intelの2019年第3四半期決算・通期見通し|https://www.intc.com/news-events/press-releases/detail/1088/intel-reports-third-quarter-2019-financial-results|2019-10-25
mu-2020q3|2020-06-29|Micronの2020年度第3四半期決算・見通し|https://www.sec.gov/Archives/edgar/data/723125/000072312520000063/a2020q3exhibit991-pres.htm|2020-06-30
tsmc-2020q2|2020-07-16|TSMCの2020年第2四半期決算|https://investor.tsmc.com/schinese/encrypt/files/encrypt_file/qr/phase5_support/2Q20EarningsRelease_1.pdf|
intel-7nm-delay|2020-07-23|Intelが7nm製造計画の遅延を公表|https://www.intc.com/news-events/press-releases/detail/1402/intel-reports-second-quarter-2020-financial-results|2020-07-24
amd-2020q2|2020-07-28|AMDの2020年第2四半期決算|https://ir.amd.com/news-events/press-releases/detail/963/amd-reports-second-quarter-2020-financial-results|2020-07-29
nvda-2020q2|2020-08-19|NVIDIAの2021年度第2四半期決算|https://www.globenewswire.com/news-release/2020/08/19/2080927/0/en/nvidia-announces-financial-results-for-second-quarter-fiscal-2021.html|2020-08-20
amd-xilinx-2020|2020-10-27|AMDがXilinx買収合意を発表|https://ir.amd.com/news-events/press-releases/detail/977/amd-to-acquire-xilinx-creating-the-industrys-high-performance-computing-leader|
pfizer-2020|2020-11-09|Pfizer・BioNTechがワクチン中間解析を発表|https://investors.biontech.de/node/8686/pdf|
fed-2021jun|2021-06-16|2021年6月FOMC声明・経済見通し|https://www.federalreserve.gov/monetarypolicy/fomcpresconf20210616.htm|
mu-2021q3|2021-06-30|Micronの2021年度第3四半期決算|https://investors.micron.com/news/press-release/2021/Micron-Technology-Inc--Reports-Results-for-the-Third-Quarter-of-Fiscal-2021-06-30-2021/default.aspx|2021-07-01
amd-2021q2|2021-07-27|AMDの2021年第2四半期決算|https://ir.amd.com/news-events/press-releases/detail/1014/amd-reports-second-quarter-2021-financial-results|2021-07-28
nvda-2021q2|2021-08-18|NVIDIAの2022年度第2四半期決算|https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2022|2021-08-19
amd-2021q3|2021-10-26|AMDの2021年第3四半期決算|https://ir.amd.com/news-events/press-releases/detail/1027/amd-reports-third-quarter-2021-financial-results|2021-10-27
amd-meta-2021|2021-11-08|AMDのデータセンター新製品とMeta採用|https://www.amd.com/en/newsroom/press-releases/2021-11-8-amd-unveils-workload-tailored-innovations-and-prod.html|
mobileye-ipo-2021|2021-12-06|IntelがMobileyeのIPO計画を発表|https://www.intc.com/news-events/press-releases/detail/1509/intel-announces-intent-to-take-mobileye-public|2021-12-07
mu-2021dec|2021-12-20|Micronの2022年度第1四半期決算|https://investors.micron.com/news/press-release/2021/Micron-Technology-Inc--Reports-Results-for-the-First-Quarter-of-Fiscal-2022-12-20-2021/default.aspx|2021-12-21
tsmc-2024jan|2024-01-18|TSMC決算と2024年の需要見通し|https://pr.tsmc.com/english/news/3101|
arm-2024feb|2024-02-07|Armの2024年度第3四半期決算|https://investors.arm.com/news-releases/news-release-details/arm-holdings-plc-reports-results-third-quarter-financial-year|2024-02-08
nvda-2024feb|2024-02-21|NVIDIAの2024年度第4四半期決算|https://investor.nvidia.com/news/press-release-details/2024/NVIDIA-Announces-Financial-Results-for-Fourth-Quarter-and-Fiscal-2024/|2024-02-22
avgo-2025sep|2025-09-04|Broadcomの2025年度第3四半期決算|https://www.broadcom.com/company/news/financial-releases/63416|
oracle-2025sep|2025-09-09|Oracleの2026年度第1四半期決算|https://investor.oracle.com/investor-news/news-details/2025/Oracle-Announces-Fiscal-Year-2026-First-Quarter-Financial-Results/default.aspx|2025-09-10
openai-avgo-2025|2025-10-13|OpenAI・BroadcomがAIアクセラレータ提携|https://openai.com/index/openai-and-broadcom-announce-strategic-collaboration/|
aws-trainium3|2025-12-02|AWS Trainium3 UltraServers一般提供開始|https://press.aboutamazon.com/2025/12/trainium3-ultraservers-now-available-enabling-customers-to-train-and-deploy-ai-models-faster-at-lower-cost|
tsmc-2026feb|2026-02-10|TSMCの2026年1月売上報告|https://pr.tsmc.com/schinese/news/3284|
amd-meta-2026|2026-02-24|AMD・Metaが6GWのGPU提携を発表|https://ir.amd.com/news-events/press-releases/detail/1279/amd-and-meta-announce-expanded-strategic-partnership-to-deploy-6-gigawatts-of-amd-gpus|
iran-ceasefire-2026|2026-04-07|米国・イランの停戦合意と原油急落|https://www.investing.com/news/stock-market-news/oil-dives-stocks-surge-as-trump-agrees-twoweek-ceasefire-4601841|2026-04-08
intel-2026apr|2026-04-23|Intelの2026年第1四半期決算|https://www.intc.com/filings-reports/all-sec-filings/content/0000050863-26-000077/q126earningsrelease.htm|2026-04-24
alphabet-2026apr|2026-04-29|Alphabetの2026年第1四半期決算|https://www.sec.gov/Archives/edgar/data/1652044/000165204426000043/googexhibit991q12026.htm|2026-04-30
nvda-2026may|2026-05-20|NVIDIAの2027年度第1四半期決算|https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2027/default.aspx|2026-05-21
deepseek-v32-exp|2025-09-29|DeepSeek V3.2-Exp発表|https://www.deepseek.com/news/|
deepseek-v32|2025-12-01|DeepSeek V3.2発表|https://www.deepseek.com/en/transparency/|
deepseek-v4|2026-04-24|DeepSeek V4プレビュー発表|https://www.deepseek.com/en/transparency/|
deepseek-v41|2026-09-10|DeepSeek V4.1 Flash発表|https://www.deepseek.com/news/|'''

ADDITIONS += '''
sept11-attacks|2001-09-11|米同時多発テロと市場休場・再開|https://www.federalreservehistory.org/essays/september-11|2001-09-17
bailout-vote-2008|2008-09-29|米下院が金融安定化法案を否決|https://www.pbs.org/newshour/economy/business-july-dec08-bailout_09-29|
microchip-warning-2014|2014-10-09|Microchipの需要警告を受けた半導体株売り|https://www.theguardian.com/business/2014/oct/10/ftse-slumps-another-14-with-chipmakers-hit-by-microchip-warning|2014-10-10
apple-warning-2019|2019-01-02|Appleが売上見通しを下方修正|https://www.apple.com/newsroom/2019/01/letter-from-tim-cook-to-apple-investors/|2019-01-03
fed-emergency-2020|2020-03-15|FRBの緊急利下げ・資産購入拡大|https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm|2020-03-16
powell-jacksonhole-2022|2022-08-26|パウエル議長のジャクソンホール講演|https://www.federalreserve.gov/newsevents/speech/files/powell20220826a.pdf|
china-curbs-2024|2024-07-17|対中半導体輸出規制強化の観測と台湾発言|https://www.youtube.com/watch?v=3iAS_cq79zs|
jobs-2024aug|2024-08-02|米国7月雇用統計公表|https://www.bls.gov/news.release/archives/empsit_08022024.htm|
asml-2024oct|2024-10-15|ASML決算の予定前公表と翌年見通し|https://www.asml.com/en/news/press-releases/2024/q3-2024-financial-results-dd3ac76a9d4d0f8c|
tariffs-2025apr|2025-04-02|米国が相互関税政策を発表|https://www.govinfo.gov/app/details/DCPD-202500423|2025-04-03
avgo-selloff-2026|2026-06-05|Broadcom決算への失望が半導体株に波及との報道|https://finance.yahoo.com/markets/stocks/articles/chip-selloff-erases-over-1-195406803.html|'''

ADDITIONS += '''
asia-selloff-1997|1997-10-27|アジア景気・需要懸念と半導体株売り|https://journalrecord.com/1997/10/27/concern-for-asian-market-leads-to-decline-in-us-stocks/|
intel-warning-2000|2000-09-21|Intelの売上見通し警告|https://abcnews.com/business/story?id=89316&page=1|2000-09-22
tsmc-2002q2|2002-07-25|TSMC決算と出荷・価格見通し|https://www.sec.gov/Archives/edgar/vprr/0204/02047320.pdf|
intel-warning-2002|2002-10-15|Intel決算と第4四半期への警告|https://money.cnn.com/2002/10/16/markets/markets_newyork/index.htm|2002-10-16
nvda-2025feb-reaction|2025-02-27|NVIDIA決算後の下落とAI投資懸念|https://ca.finance.yahoo.com/news/nasdaq-futures-lead-gains-nvidia-111555640.html|'''

NOTES = {
    'pentiumii-1997': '公式年表で投入日を確認。5月2日の始点より後なので、その始点のきっかけには使わない。',
    'intel-7nm-delay': '7nm工程の歩留まりが社内目標より約12か月遅れていると公表。Intelと競合企業への影響は分ける。',
    'amd-xilinx-2020': '買収合意の発表。取引成立は2022年で、この日とは異なる。',
    'mobileye-ipo-2021': '米国市場引け後のIPO方針の発表。実際の上場日ではない。',
    'iran-ceasefire-2026': '米国7日夜の合意を受け、翌8日は原油下落・幅広い株式上昇とReutersが報道。半導体への資金集中という指定仮説とは別の説明候補。',
    'china-tariff-2019sep': 'Reuters当日報道は、関税除外と技術株買いを関連付け、SOX上昇も記載。因果の実証ではない。',
    'amd-meta-2026': '6GW規模の複数年GPU提携を公表。契約・計画と実際の売上計上は異なる。',
    'openai-avgo-2025': '10GW規模の独自AIアクセラレータ協業計画を公表。納入完了を意味しない。',
    'tsmc-2026feb': '1月売上が前年同月比36.8％増と公式発表。',
    'deepseek-v41': '公式発表を確認。9月14日のSOX急落に近いが、因果を裏付ける報道は今回確認できていない。',
    'sept11-attacks': '9月11日のテロで市場が休場し、17日に再開。休場中の出来事を再開日に対応させる。',
    'bailout-vote-2008': '法案否決と株価急落をPBSが当日報道。金融危機下の複数要因の一つ。',
    'microchip-warning-2014': '需要警告と半導体株下落を当日報道が関連付けた。SOX単独の因果効果は未推計。',
    'apple-warning-2019': 'Appleが投資家向け書簡で売上見通しを修正。サプライチェーンの需要懸念を考える材料。',
    'fed-emergency-2020': '新型コロナ下の金融緩和措置。緩和そのものが急落を引き起こしたとは断定しない。',
    'powell-jacksonhole-2022': 'インフレ抑制に向けた金融政策姿勢を示した講演。',
    'china-curbs-2024': 'Reuters当日報道が、規制強化観測・台湾防衛発言と半導体株下落を関連付けた。',
    'asml-2024oct': 'ASMLが決算を予定より早く公表した事実と、2025年の見通しを確認。',
    'tariffs-2025apr': '米国引け後の関税政策発表。半導体への直接適用範囲と、需要・景気への懸念は別。',
    'avgo-selloff-2026': 'Reuters当日報道は、先行するBroadcom決算への失望の波及を説明候補に挙げた。',
    'asia-selloff-1997': 'Bloomberg当日報道はアジア経済減速と半導体需要への懸念を説明候補に挙げた。',
    'intel-warning-2000': '売上見通し警告と翌22日のIntel株下落をABC Newsが報道。',
    'tsmc-2002q2': '次四半期の出荷減・平均販売価格低下の見通しを公式資料で確認。SOX急落の単独原因とは断定しない。',
    'intel-warning-2002': '15日夜の決算・警告を受けた翌16日の技術株下落をCNNが報道。',
    'nvda-2025feb-reaction': 'ReutersはNVIDIA決算後の下落とAI投資懸念を報道。1月のDeepSeek懸念にも触れるが、独立した第2回DeepSeekショックと断定しない。',
}

def main():
    path=DATA/'events.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    existing={e['id'] for e in data['events']}
    for row in ADDITIONS.splitlines():
        id,day,title,url,market=row.split('|')
        if id in existing:
            continue
        report=any(host in url for host in ['investing.com','pbs.org','theguardian.com','youtube.com','finance.yahoo.com','journalrecord.com','abcnews.com','money.cnn.com'])
        note=NOTES.get(id,'発表日と内容を公式資料で確認した、時期の近い候補。値動きの原因や寄与率を実証したものではない。')
        if id.startswith('deepseek-') and id not in NOTES:
            note='モデルの発表は公式確認。発表があっただけで独立した「ショック」とは呼ばず、SOXの騰落を別に示す。'
        item=dict(id=id,date=day,title=title,short=title,kind='macro' if id.startswith(('fed-','iran-','china-','pfizer-','sept11-','bailout-','jobs-','powell-','tariffs-')) else 'industry',evidence='当日の報道で確認' if report else '公式確認',note=note,sources=[dict(label='当日の報道' if report else '発表元・公的機関の資料',url=url)])
        if market:
            item['market_date']=market
        data['events'].append(item)
    for event in data['events']:
        if event['date']=='2026-10-17' and 'deepseek' in event['id'].lower():
            event['title']='DeepSeek新モデル発表(ショックなし)'
            event['short']=event['title']
            event['note']=event['note'].replace('DeepSeekショック（ショックにならなかった）',event['title'])
    if not any(p['title'].startswith('DeepSeek') for p in data['pending']):
        data['pending'].append({'title':'DeepSeekショックの回数の同定','note':'2025年1月27日の急落と、複数のモデル発表を区別。2025年9月・12月、2026年4月・9月・10月の発表を追加したが、独立したショックが2〜3回あったとの根拠は今回確認できていない。2026年9月14日の急落と9月10日の発表も因果未確認。'})
    data['events'].sort(key=lambda e:(e['date'],e['id']))
    data['scope']='半導体史の主要事象と、高値更新直前1〜14暦日のニュース候補。原因や網羅性を保証しない。'
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('events:',len(data['events']))

if __name__=='__main__':
    main()
