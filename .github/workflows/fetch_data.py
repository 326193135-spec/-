import json
from datetime import datetime, timedelta
import akshare as ak
import pandas as pd

def get_recent_trade_dates(days=5):
    # 获取A股交易日历
    trade_cal = ak.tool_trade_date_hist_sina()
    today_str = datetime.now().strftime("%Y-%m-%d")
    valid_dates = trade_cal[trade_cal['trade_date'].astype(str) <= today_str]['trade_date'].astype(str).tolist()
    return [d.replace("-", "") for d in valid_dates[-days:]]

def is_main_board(code, name):
    # 过滤沪深主板（60/00开头，排除ST）
    if "ST" in name or "退" in name:
        return False
    return str(code).startswith(("600", "601", "603", "605", "000", "001", "002", "003"))

def format_time(t_str):
    # 将 093512 格式化为 09:35
    s = str(t_str).zfill(6)
    return f"{s[:2]}:{s[2:4]}"

def time_diff_minutes(t1, t2):
    fmt = "%H:%M"
    dt1 = datetime.strptime(t1, fmt)
    dt2 = datetime.strptime(t2, fmt)
    return abs((dt1 - dt2).total_seconds()) / 60.0

def build_market_data():
    dates = get_recent_trade_dates(5)
    history_data = {}

    for d in dates:
        # 1. 获取当日涨停股池 (东财接口)
        zt_df = ak.stock_zt_pool_em(date=d)
        # 2. 获取当日炸板股池
        zb_df = ak.stock_zt_pool_zbgc_em(date=d)
        # 3. 获取昨日涨停股池（用于追踪高位断板）
        prev_zt_df = ak.stock_zt_pool_previous_em(date=d)

        zt_list = []
        if zt_df is not None and not zt_df.empty:
            for _, row in zt_df.iterrows():
                code = str(row['代码'])
                name = str(row['名称'])
                if not is_main_board(code, name):
                    continue
                zt_list.append({
                    "code": code,
                    "name": name,
                    "boards": int(row['连板数']),
                    "time": format_time(row['首次封板时间']),
                    "sector": str(row['所属行业']),
                    "status": "limit_up",
                    "kawei_target": None
                })

        # 识别昨日 >= 3连板 且今日未涨停的高位断板股
        broken_high_stocks = []
        zt_codes = {item['code'] for item in zt_list}
        if prev_zt_df is not None and not prev_zt_df.empty:
            for _, row in prev_zt_df.iterrows():
                code = str(row['代码'])
                name = str(row['名称'])
                yesterday_boards = int(row['昨日连板数'])
                if is_main_board(code, name) and yesterday_boards >= 3 and code not in zt_codes:
                    # 尝试从炸板池找炸板时间，若未炸板则取开盘竞价/分歧时间 09:30
                    break_time = "09:30"
                    if zb_df is not None and not zb_df.empty and code in zb_df['代码'].values:
                        zb_row = zb_df[zb_df['代码'] == code].iloc[0]
                        break_time = format_time(zb_row['首次封板时间'])
                    broken_high_stocks.append({
                        "code": code,
                        "name": name,
                        "yesterday_boards": yesterday_boards,
                        "break_time": break_time,
                        "sector": str(row['所属行业'])
                    })

        # 自动匹配同刻卡位（高位断板前后 ±3 分钟内上板的标的）
        for stock in zt_list:
            for broken in broken_high_stocks:
                if time_diff_minutes(stock['time'], broken['break_time']) <= 3:
                    stock['kawei_target'] = f"⚡{stock['time']}卡位 {broken['name']}({broken['yesterday_boards']}板断)"
                    break

        history_data[d] = {
            "limit_up": zt_list,
            "broken_high": broken_high_stocks
        }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
    print(f"[{datetime.now()}] 数据更新完成，已写入 data.json")

if __name__ == "__main__":
    build_market_data()
