#!/usr/bin/env sh
./skrapa.py \
--config='.secrets' \
--output='../output' \
--cache='../cache' \
--profile='../firefox-profile' \
--headless \
--export-cache='../exported_pages' \
--suppress-errors \
$1

