#!/usr/bin/env python3
# send path/to/output/folder
# loop over items in folder

# email
import smtplib
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import formatdate
from email import encoders

# configs
import configparser
import sys


def send_mail(
    send_from,
    send_to,
    subject,
    message,
    files=[],
    server="localhost",
    port=587,
    username="",
    password="",
    use_tls=True,
):
    """Compose and send email with provided info and attachments.

    Args:
        send_from (str): from name
        send_to (list[str]): to name(s)
        subject (str): message title
        message (str): message body
        files (list[str]): list of file paths to be attached to email
        server (str): mail server host name
        port (int): port number
        username (str): server auth username
        password (str): server auth password
        use_tls (bool): use TLS mode

    Adapted from https://stackoverflow.com/questions/3362600/how-to-send-email-attachments
    """
    msg = MIMEMultipart()
    msg["From"] = send_from
    msg["To"] = send_to
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    msg.attach(MIMEText(message))

    for path in files:
        part = MIMEBase("application", "octet-stream")
        with open(path, "rb") as file:
            part.set_payload(file.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", 'attachment; filename="{}"'.format(Path(path).name)
        )
        msg.attach(part)

    smtp = smtplib.SMTP(server, port)
    if use_tls:
        smtp.starttls()
    smtp.login(username, password)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.quit()


if __name__ == "__main__":
    secrets = configparser.ConfigParser()
    secrets.read(".secrets")
    conf = secrets["email"]
    folder_to_send = Path(sys.argv[1])
    if not folder_to_send.is_dir():
        raise FileNotFoundError(f"{folder_to_send} is not a valid directory")
    else:
        send_mail(
            send_from=conf["from"],
            send_to=conf["recipients"],
            subject=conf["subject"],
            message=conf["message"],
            files=folder_to_send.glob("*.xlsx"),
            server=conf["smtp"],
            port=int(conf["port"]),
            username=conf["username"],
            password=conf["password"],
        )
