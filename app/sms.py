"""Отправка SMS. Сейчас — заглушка, пишет в лог.
Для запуска подключить казахстанского SMS-провайдера: заменить тело send_sms."""
import logging

log = logging.getLogger("usta.sms")


def send_sms(phone: str, text: str) -> None:
    log.info("SMS to %s: %s", phone, text)
