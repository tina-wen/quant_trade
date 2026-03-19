from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


# 从tushare读取合约的保证金率、费率等数据，保存到本地MySQL
def test_save_contract_from_ts():
    from vnpy.trader.constant import Exchange

    from get_data import get_contract_info
    from scripts.data.ts_download import save_ts_contr

    save_ts_contr("RB1905", Exchange.SHFE, datetime(2018, 6, 1), datetime(2019, 6, 15))
    long_margin = get_contract_info("RB1905", datetime(2019, 4, 8), "long_margin")
    assert long_margin == 0.1, (
        f"Expected long_margin of RB1905 on 2019-04-08 is 0.1, but got {long_margin}"
    )
    settle_price = get_contract_info("RB1905", datetime(2018, 9, 18), "settle")
    assert settle_price == 3839.0, (
        f"Expected settle of RB1905 on 2018-09-18 is 3839.0, but got {settle_price}"
    )


# 从csv读取ohlc价格时序，保存到本地MySQL
def test_save_bar_from_csv():
    import numpy as np
    from vnpy.trader.constant import Exchange, Interval

    from get_data import DataQuery
    from scripts.data.ts_download import save_csv_bar

    save_csv_bar("datasets/price.csv", "Unnamed: 0", "test_A1301", Interval.DAILY, "SHFE")

    start_time, end_time = (
        datetime.strptime("2011-9-15", "%Y-%m-%d"),
        datetime.strptime("2013-01-16", "%Y-%m-%d"),
    )
    data_query = DataQuery(
        "test_A1301", start_time, end_time, Interval.DAILY, exchange=Exchange.SHFE
    )

    # 判断ohls数据是否正确提取，均值、最大、最小、标准差
    mean_open = round(sum(data_query.open_price) / len(data_query.open_price), 1)
    max_high = max(data_query.high_price)
    min_low = min(data_query.low_price)
    settle_std = round(np.std(data_query.settle_price, ddof=1), 2)

    assert mean_open == 4541.0, (
        f"Expected mean open_price from {start_time} to {end_time} is 4541.0, got {mean_open}"
    )
    assert max_high == 5008.0, (
        f"Expected max high_price from {start_time} to {end_time} is 5008.0, got {max_high}"
    )
    assert min_low == 4146.0, (
        f"Expected min low_price from {start_time} to {end_time} is 4146.0, got {min_low}"
    )
    assert settle_std == 194.26, (
        f"Expected std settle_price from {start_time} to {end_time} is 194.26, got {settle_std}"
    )


# 从tushare读取ohlc价格时序，保存到本地MySQL
def test_save_bar_from_ts():
    import numpy as np
    from vnpy.trader.constant import Exchange, Interval

    from get_data import DataQuery
    from scripts.data.ts_download import save_ts_bar

    save_ts_bar(
        "CU1911", Exchange.SHFE, datetime(2018, 10, 1), datetime(2019, 12, 1), Interval.DAILY
    )

    start_time, end_time = (
        datetime.strptime("2018-12-15", "%Y-%m-%d"),
        datetime.strptime("2019-06-16", "%Y-%m-%d"),
    )
    data_query = DataQuery(
        "CU1911",
        start_time,
        end_time,
        Interval.DAILY,
    )

    # 判断ohls数据是否正确提取，均值、最大、最小、标准差
    mean_open = round(sum(data_query.open_price) / len(data_query.open_price), 1)
    max_high = max(data_query.high_price)
    min_low = min(data_query.low_price)
    settle_std = round(np.std(data_query.settle_price, ddof=1), 2)

    assert mean_open == 48339.0, (
        f"Expected mean open_price from {start_time} to {end_time} is 48339.0, got {mean_open}"
    )
    assert max_high == 50660.0, (
        f"Expected max high_price from {start_time} to {end_time} is 50660.0, got {max_high}"
    )
    assert min_low == 46030.0, (
        f"Expected min low_price from {start_time} to {end_time} is 46030.0, got {min_low}"
    )
    assert settle_std == 1049.68, (
        f"Expected std settle_price from {start_time} to {end_time} is 1049.68, got {settle_std}"
    )
