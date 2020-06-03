#!/usr/bin/env sh
cd ~/apotekstider
./skrapa \
--output='../output' \
--cache='../cache' \
--export-cache='../exported_pages' \
--suppress-errors \
--exec='./misc/send_output_files_with_email.py --export-cache={} {}' \
ALLA && shutdown

