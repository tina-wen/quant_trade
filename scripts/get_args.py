import argparse


def parse_mixed_value(value):
    """Parse CLI value into float, string, or None."""
    if value.lower() == "none":
        return None
    try:
        return float(value)
    except ValueError:
        return value


def get_args(argv=None):
    parser = argparse.ArgumentParser(description="")

    parser.add_argument("--usr_name", type=str, default="demo", help="usr_name")
    parser.add_argument("--init_fund", type=float, default=1000000, help="init_funds")
    parser.add_argument("--margin_call", type=float, default=100000.00)

    parser.add_argument("--code", type=str, required=True, help="contract code")

    parser.add_argument("--target", type=str, default="open")
    parser.add_argument("--source", type=str)
    parser.add_argument(
        "--start_time",
        type=str,
    )
    parser.add_argument(
        "--end_time",
        type=str,
    )
    parser.add_argument("--open", type=str, default="open")
    parser.add_argument("--high", type=str, default="high")
    parser.add_argument("--low", type=str, default="low")
    parser.add_argument("--settle", type=str, default="settle")

    parser.add_argument("--shares", type=int, default=1)

    parser.add_argument("--stop_loss", type=float, default=0.1)
    parser.add_argument(
        "--slippage", type=float, default=0.0, help="滑点，买入加价、卖出减价（价格单位）"
    )

    parser.add_argument("--input_mode", type=str, default="in")
    parser.add_argument(
        "--trade_strategy",
        type=str,
    )
    parser.add_argument("--lag", type=int, default=5)
    parser.add_argument("--short", type=int, default=5)
    parser.add_argument("--long", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=1.0)

    parser.add_argument("--ubr", type=float, default=0.75)
    parser.add_argument("--lbr", type=float, default=0.25)
    parser.add_argument("--level", type=float, default=4500.00)

    parser.add_argument("--log_dir", type=str)

    parser.add_argument(
        "--sim",
        action="store_true",
        default=False,
        help="Run in simulation mode using fake_stream instead of the database",
    )
    parser.add_argument(
        "--sim_num_klines",
        type=int,
        default=200,
        help="Number of synthetic bars to generate in simulation mode",
    )
    parser.add_argument(
        "--sim_volatility",
        type=float,
        default=0.02,
        help="Per-bar price volatility in simulation mode",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="d",
        help="Bar interval in vn.py format (e.g. d, w, 1m, 1h)",
    )
    args = parser.parse_args(argv)

    args.config = {
        k: v
        for k, v in vars(args).items()
        if k in {"source", "lag", "short", "long", "threshold", "ubr", "lbr", "level"}
    }
    args.query_config = {
        k: v for k, v in vars(args).items() if k in {"target", "settle", "open", "high", "low"}
    }
    return args
