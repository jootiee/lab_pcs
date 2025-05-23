#!/usr/bin/env python3

import argparse
import os
import re
import base64
import numpy as np
import cv2
from ultralytics import YOLO
from time import sleep
import sys
import platform
from typing import Optional

from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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


def get_system_info() -> Optional[dict]:
    system = platform.system().lower()
    if system != "linux":
        print("This script only works on Linux systems.")
        sys.exit(1)

    distro = ""
    version = ""

    try:
        os_release = platform.freedesktop_os_release()
        distro = os_release.get('ID', '').lower()
        version = os_release.get('VERSION_ID', '')
    except (AttributeError, OSError, FileNotFoundError):
        pass

    if not distro or not version:
        if os.path.exists("/etc/debian_version"):
            distro = "debian"
            with open("/etc/debian_version", "r") as f:
                version = f.read().strip()
        elif os.path.exists("/etc/fedora-release"):
            distro = "fedora"
            with open("/etc/fedora-release", "r") as f:
                version_match = re.search(r'release (\d+)', f.read())
                if version_match:
                    version = version_match.group(1)
        elif os.path.exists("/etc/arch-release"):
            distro = "archlinux"
            version = "rolling"

    arch = platform.machine().lower()

    if arch in ["x86_64", "amd64"]:
        arch_type = "intel"
    elif arch in ["aarch64", "arm64", "armv8"]:
        arch_type = "arm"
    else:
        arch_type = "other"

    return {
        "system": system,
        "distro": distro,
        "version": version,
        "arch": arch,
        "arch_type": arch_type
    }


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
                ActionChains(driver).move_to_element(img).click().perform()
                counter += 1
                if counter == 3:
                    return
            sleep(0.25)


def get_candidates(
    driver: Driver,
    package_name: str
) -> Optional[dict]:
    driver.get("https://pkgs.org/search/?q=" + package_name)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "container"))
    )

    if driver.find_elements(By.ID, "consent_notice"):
        driver.find_element(By.ID, "consent_notice_agree").click()

    print("Testing if captcha is present...")
    while len(driver.find_elements(By.ID, "captcha")):
        print("Captcha is present, solving...")
        solve_captcha(driver)
        sleep(0.5)
    print("Captcha is solved!")

    candidate_buttons = driver.find_elements(
        By.CLASS_NAME, "card")

    if not candidate_buttons:
        print(f'No candidates for query "{package_name}" found.')
        return None

    result = {}
    print("Found candidates:", len(candidate_buttons))
    print("Parsing candidates...")
    for i, section in enumerate(candidate_buttons):
        candidate = dict()
        try:
            if i:
                ActionChains(driver).move_to_element(section).click().perform()

            distro_name = section.find_element(
                By.CLASS_NAME, "card-title").text.strip()

            rows = section.find_elements(
                By.TAG_NAME, "tr")

            subsection_name = ""
            for row in rows:
                if row.get_attribute("class") == "table-active":
                    subsection_name = row.text.strip()
                    candidate[subsection_name] = list()
                else:
                    tds = row.find_elements(By.TAG_NAME, "td")
                    candidate[subsection_name].append({
                        "link":         tds[0].find_element(By.TAG_NAME, "a").get_attribute("href"),
                        "description":  tds[1].text.strip()
                    })

            result[distro_name] = candidate
        except Exception as e:
            print("exception:", e)
            continue

    return result


def select_from_list(data: list) -> int:
    while True:
        print("Available candidates:")
        for i, elem in enumerate(data):
            print(f"{i + 1}. {elem}")
        print("0. Exit")

        choice = input("Select a candidate (0 to exit): ")
        if choice.isdigit():
            choice = int(choice)
            if 0 <= choice <= len(data):
                if choice == 0:
                    return -1
                return choice - 1
            else:
                print("Invalid choice. Please try again.")
        else:
            print("Invalid input. Please enter a number.")


def select_candidate_prompt(candidates: dict) -> str:
    # select distro
    distros = list(candidates.keys())
    ind_distro = select_from_list(distros)
    print("Selected distro:", distros[ind_distro])
    versions = list(candidates[distros[ind_distro]].keys())
    ind_version = select_from_list(versions)
    print("Selected version:", versions[ind_version])
    packages = list(candidates[distros[ind_distro]]
                    [versions[ind_version]].keys())
    ind_package = select_from_list(packages)
    print("Selected package:", packages[ind_package])
    links = list(candidates[distros[ind_distro]]
                 [versions[ind_version]][packages[ind_package]].keys())
    ind_link = select_from_list(links)

    return links[ind_link]


def main(args):
    package_name = args.package_name
    proxy = args.proxy

    if proxy is not None:
        if not validate_proxy(proxy):
            print(f"Invalid proxy format: {proxy}.")
            return

    driver = Driver(uc=True,
                    headless=True,
                    # headless=False,
                    agent=AGENT,
                    proxy=proxy)

    candidates = get_candidates(driver, package_name)
    with open("candidates.json", "w") as file:
        import json
        json.dump(candidates, file, indent=4)
    res = select_candidate_prompt(candidates)
    print(res)


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

    args = parser.parse_args()
    print("Loading...")
    model = YOLO("model.pt")

    main(args)
