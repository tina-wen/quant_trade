#!/bin/bash

export PYTHONDONTWRITEBYTECODE=1

usr_name=demo

init_fund=1000000
open_code=CU1911

n_shares=1

# 数据读取
open_col=open
close_col=close
strategy=dma

log_path=logs/${usr_name}/${open_code}_${strategy}
mkdir $log_path

python backtest_exec.py \
	--usr_name ${usr_name} \
	--init_fund $init_fund \
	--code $open_code \
	--shares $n_shares \
	--start_time 2018-12-15 \
	--source $close_col \
	--end_time 2019-06-16 \
	--log_dir $log_path \
	--trade_strategy ${strategy} \
	--stop_loss float 0.1 None \
