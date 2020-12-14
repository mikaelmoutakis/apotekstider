#!/usr/bin/env sh
./skrapa.py \
--config='.secrets' \
--profile='../selenium-profile' \
--output='../output' \
--headless \
--cache='../cache' \
--export-cache='../exported_pages' \
--suppress-errors \
$1

#--headless \