#!/usr/bin/env python3

import argparse
import os
import re
import base64
import numpy as np
import cv2
from ultralytics import YOLO
from time import sleep

from seleniumbase import Driver
from selenium.webdriver.common.by import By

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

CLASS_NAMES = (
    "bird",
    "butterfly",
    "cat",
    "dinosaur",
    "dog",
    "fish",
    "horse"
)


def validate_proxy(proxy: str) -> bool:
    pattern = r"^http:\/\/[a-zA-Z0-9.\-]+(:[0-9]{1,5})$"
    return bool(re.match(pattern, proxy))


def has_object(image: str, object_name: str, conf: float = 0.5) -> bool:
    if object_name not in CLASS_NAMES:
        raise ValueError(f"Unknown object name: {object_name}")

    img_bytes = base64.b64decode(image)
    img_array = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    class_id = CLASS_NAMES.index(object_name)
    results = model(img, conf=conf, verbose=False)
    for r in results:
        if r.boxes is not None and len(r.boxes.cls) > 0:
            if any(int(cls) == class_id for cls in r.boxes.cls):
                return True
    return False


def solve_captcha(driver: Driver):
    table = driver.find_element(By.ID, "captcha")
    xpath = "//span[contains(@class, 'badge') and contains(@class, 'badge-pill') and contains(@class , 'text-bg-danger')]"
    expected = driver.find_element(By.XPATH, xpath).text
    rows = table.find_elements(By.TAG_NAME, "tr")
    counter = 0
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        for cell in cells:
            img = cell.find_element(By.TAG_NAME, "img")
            if has_object(image=img.get_attribute("src").split(",")[1],
                          object_name=expected):
                img.click()
                counter += 1
                if counter == 3:
                    return
            sleep(0.25)


def search_package(driver: Driver, package_name: str):
    page_url = "https://pkgs.org/search/?q=" + package_name
    driver.get(page_url)
    sleep(1)

    # test if captcha is present
    print("testing if captcha is present...")
    while len(driver.find_elements(By.ID, "captcha")):
        print("Captcha is present, solving...")
        solve_captcha(driver)
        sleep(0.5)
    print("Captcha solved!")

    accordion = driver.find_elements(By.ID, "tab-name-accordion")
    if len(accordion) == 0:
        print("No packages found.")
        return

    accordion = accordion[0]
    rows = accordion.find_elements(By.CLASS_NAME, "card")
    for row in rows:
        print(row)


def main(args):
    package_name = args.package_name
    proxy = args.proxy
    if proxy is not None:
        if not validate_proxy(proxy):
            print(f"Invalid proxy format: {proxy}.")
            return

    driver = Driver(uc=True,
                    # headless=True,
                    headless=False,
                    agent=AGENT,
                    proxy=proxy)

    search_package(driver, package_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="This program eases installation of packages from pkgs.org",
        epilog="This program is a part of the project for HSE course 'Python Client-Server Programming'.",
    )
    parser.add_argument("package_name", type=str,
                        help="Name of the package to install")

    parser.add_argument("proxy",
                        type=str,
                        help="HTTP proxy server address (e.g., http://127.0.0.1:8080)",
                        default=None,
                        nargs="?")
    model = YOLO("model.pt")

    args = parser.parse_args()

    main(args)
