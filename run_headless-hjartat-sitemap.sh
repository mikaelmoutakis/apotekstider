#!/usr/bin/env sh
cd ~/apotekstider
./skrapa \
--save-sitemap \
--profile='../firefox-profile' \
--output='../output' \
--cache='../cache' \
--headless \
--suppress-errors \
--exec='./misc/send_output_files_with_email.py {}' \
hjartat

