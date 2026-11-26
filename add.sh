#!/bin/sh
# 使い方: sh add.sh <code> <name>  (標準入力: 日付 現物買 新規買 返済買 現物売 新規売 返済売 空売り  ※千株・出来高は買い合計で補う)
awk '{printf "%s %s %s %s %s %s %s %s %.3f\n",$1,$2,$3,$4,$5,$6,$7,$8,$2+$3+$4}' | PYTHONIOENCODING=utf-8 python add_jukyu_rows.py "$1" "$2" --unit sen
