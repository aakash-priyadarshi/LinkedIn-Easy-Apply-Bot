from __future__ import annotations

import json
import csv
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta
import getpass
from pathlib import Path

import pandas as pd
import pyautogui
import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager


log = logging.getLogger(__name__)


def setupLogger() -> None:
    dt: str = datetime.strftime(datetime.now(), "%m_%d_%y %H_%M_%S ")

    if not os.path.isdir('./logs'):
        os.mkdir('./logs')

    # TODO need to check if there is a log dir available or not
    logging.basicConfig(filename=('./logs/' + str(dt) + 'applyJobs.log'), filemode='w',
                        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s', datefmt='./logs/%d-%b-%y %H:%M:%S')
    log.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    c_handler.setFormatter(c_format)
    log.addHandler(c_handler)


class EasyApplyBot:
    setupLogger()
    # MAX_SEARCH_TIME is 10 hours by default, feel free to modify it
    MAX_SEARCH_TIME = 60 * 60

    def __init__(self,
                 username,
                 password,
                 phone_number,
                 salary,
                 rate,
                 uploads={},
                 filename='output.csv',
                 blacklist=[],
                 blackListTitles=[],
                 experience_level=[]
                 ) -> None:

        # Convert relative paths to absolute paths for uploads
        for key, path in uploads.items():
            if not os.path.isabs(path):
                uploads[key] = os.path.abspath(path)
                log.info(f"Converting {key} path to absolute: {uploads[key]}")

        self.uploads = uploads
        self.salary = salary
        self.rate = rate
        past_ids: list | None = self.get_appliedIDs(filename)
        self.appliedJobIDs: list = past_ids if past_ids != None else []
        self.filename: str = filename
        self.options = self.browser_options()
        self.browser = webdriver.Chrome(service=ChromeService(
            ChromeDriverManager().install()), options=self.options)
        self.wait = WebDriverWait(self.browser, 30)
        self.blacklist = blacklist
        self.blackListTitles = blackListTitles
        self.phone_number = phone_number
        self.experience_level = experience_level

        # Initialize questions and answers file with absolute path
        self.qa_file = os.path.abspath("qa.csv")
        self.answers = {}

        # Load or create QA file
        if os.path.isfile(self.qa_file):
            try:
                df = pd.read_csv(self.qa_file, encoding='utf-8')
                self.answers = dict(
                    zip(df['Question'].str.lower(), df['Answer']))
                log.info(f"Loaded {len(self.answers)
                                   } QA pairs from {self.qa_file}")
            except Exception as e:
                log.error(f"Error loading QA file: {str(e)}")
                self.answers = {}
        else:
            df = pd.DataFrame(columns=["Question", "Answer"])
            df.to_csv(self.qa_file, index=False, encoding='utf-8')
            log.info(f"Created new QA file at {self.qa_file}")

        log.info("Welcome to Easy Apply Bot")
        dirpath: str = os.getcwd()
        log.info("current directory is : " + dirpath)
        log.info("Please wait while we prepare the bot for you")
        if experience_level:
            experience_levels = {
                1: "Entry level",
                2: "Associate",
                3: "Mid-Senior level",
                4: "Director",
                5: "Executive",
                6: "Internship"
            }
            applied_levels = [experience_levels[level]
                              for level in experience_level]
            log.info("Applying for experience level roles: " +
                     ", ".join(applied_levels))
        else:
            log.info("Applying for all experience levels")

        self.start_linkedin(username, password)

        self.locator = {
            "next": (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
            "review": (By.CSS_SELECTOR, "button[aria-label='Review your application']"),
            "submit": (By.CSS_SELECTOR, "button[aria-label='Submit application']"),
            "error": (By.CLASS_NAME, "artdeco-inline-feedback__message"),
            "upload_resume": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]"),
            "upload_cv": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]"),
            "follow": (By.CSS_SELECTOR, "label[for='follow-company-checkbox']"),
            "upload": (By.NAME, "file"),
            "search": (By.CLASS_NAME, "jobs-search-results-list"),
            "links": ("xpath", '//div[@data-job-id]'),
            "fields": (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping"),
            # need to append [value={}].format(answer)
            "radio_select": (By.CSS_SELECTOR, "input[type='radio']"),
            "multi_select": (By.XPATH, "//*[contains(@id, 'text-entity-list-form-component')]"),
            "text_select": (By.CLASS_NAME, "artdeco-text-input--input"),
            "2fa_oneClick": (By.ID, 'reset-password-submit-button'),
            "easy_apply_button": (By.XPATH, '//button[contains(@class, "jobs-apply-button")]')

        }

    def get_appliedIDs(self, filename) -> list | None:
        try:
            df = pd.read_csv(filename,
                             header=None,
                             names=['timestamp', 'jobID', 'job',
                                    'company', 'attempted', 'result'],
                             lineterminator='\n',
                             encoding='utf-8')

            df['timestamp'] = pd.to_datetime(
                df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            jobIDs: list = list(df.jobID)
            log.info(f"{len(jobIDs)} jobIDs found")
            return jobIDs
        except Exception as e:
            log.info(
                str(e) + "   jobIDs could not be loaded from CSV {}".format(filename))
            return None

    def browser_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        # options.add_argument(r'--remote-debugging-port=9222')
        # options.add_argument(r'--profile-directory=Person 1')

        # Disable webdriver flags or you will be easily detectable
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Load user profile
        # options.add_argument(r"--user-data-dir={}".format(self.profile_path))
        return options

    def start_linkedin(self, username, password) -> None:
        log.info("Logging in.....Please wait :)  ")
        self.browser.get("https://www.linkedin.com/login/")
        try:
            user_field = self.browser.find_element("id", "username")
            pw_field = self.browser.find_element("id", "password")
            login_button = WebDriverWait(self.browser, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[@type='submit' and contains(@class, 'btn__primary--large')]"))
            )

            user_field.send_keys(username)
            user_field.send_keys(Keys.TAB)
            time.sleep(2)
            pw_field.send_keys(password)
            time.sleep(2)
            login_button.click()
            time.sleep(15)
            # if self.is_present(self.locator["2fa_oneClick"]):
            #     oneclick_auth = self.browser.find_element(by='id', value='reset-password-submit-button')
            #     if oneclick_auth is not None:
            #         log.info("additional authentication required, sleep for 15 seconds so you can do that")
            #         time.sleep(15)
            # else:
            #     time.sleep()
        except TimeoutException:
            log.info(
                "TimeoutException! Username/password field or login button not found")

    def fill_data(self) -> None:
        self.browser.set_window_size(1, 1)
        self.browser.set_window_position(2000, 2000)

    def start_apply(self, positions, locations) -> None:
        start: float = time.time()
        self.fill_data()
        self.positions = positions
        self.locations = locations
        combos: list = []
        while len(combos) < len(positions) * len(locations):
            position = positions[random.randint(0, len(positions) - 1)]
            location = locations[random.randint(0, len(locations) - 1)]
            combo: tuple = (position, location)
            if combo not in combos:
                combos.append(combo)
                log.info(f"Applying to {position}: {location}")
                location = "&location=" + location
                self.applications_loop(position, location)
            if len(combos) > 500:
                break

    # self.finish_apply() --> this does seem to cause more harm than good, since it closes the browser which we usually don't want, other conditions will stop the loop and just break out

    def applications_loop(self, position, location):

        count_application = 0
        count_job = 0
        jobs_per_page = 0
        start_time: float = time.time()

        log.info("Looking for jobs.. Please wait..")

        self.browser.set_window_position(1, 1)
        self.browser.maximize_window()
        self.browser, _ = self.next_jobs_page(
            position, location, jobs_per_page, experience_level=self.experience_level)
        log.info("Looking for jobs.. Please wait..")

        while time.time() - start_time < self.MAX_SEARCH_TIME:
            try:
                log.info(f"{(self.MAX_SEARCH_TIME - (time.time() -
                         start_time)) // 60} minutes left in this search")

                # sleep to make sure everything loads, add random to make us look human.
                randoTime: float = random.uniform(1.5, 2.9)
                log.debug(f"Sleeping for {round(randoTime, 1)}")
                # time.sleep(randoTime)
                self.load_page(sleep=0.5)

                # LinkedIn displays the search results in a scrollable <div> on the left side, we have to scroll to its bottom

                # scroll to bottom

                if self.is_present(self.locator["search"]):
                    scrollresults = self.get_elements("search")
                    #     self.browser.find_element(By.CLASS_NAME,
                    #     "jobs-search-results-list"
                    # )
                    # Selenium only detects visible elements; if we scroll to the bottom too fast, only 8-9 results will be loaded into IDs list
                    for i in range(300, 3000, 100):
                        self.browser.execute_script(
                            "arguments[0].scrollTo(0, {})".format(i), scrollresults[0])
                    scrollresults = self.get_elements("search")
                    # time.sleep(1)

                # get job links, (the following are actually the job card objects)
                if self.is_present(self.locator["links"]):
                    links = self.get_elements("links")
                # links = self.browser.find_elements("xpath",
                #     '//div[@data-job-id]'
                # )

                    jobIDs = {}  # {Job id: processed_status}

                    # children selector is the container of the job cards on the left
                    for link in links:
                        if 'Applied' not in link.text:  # checking if applied already
                            if link.text not in self.blacklist:  # checking if blacklisted
                                jobID = link.get_attribute("data-job-id")
                                if jobID == "search":
                                    log.debug(
                                        "Job ID not found, search keyword found instead? {}".format(link.text))
                                    continue
                                else:
                                    jobIDs[jobID] = "To be processed"
                    if len(jobIDs) > 0:
                        self.apply_loop(jobIDs)
                    self.browser, jobs_per_page = self.next_jobs_page(position,
                                                                      location,
                                                                      jobs_per_page,
                                                                      experience_level=self.experience_level)
                else:
                    self.browser, jobs_per_page = self.next_jobs_page(position,
                                                                      location,
                                                                      jobs_per_page,
                                                                      experience_level=self.experience_level)

            except Exception as e:
                print(e)

    def apply_loop(self, jobIDs):
        for jobID in jobIDs:
            if jobIDs[jobID] == "To be processed":
                applied = self.apply_to_job(jobID)
                if applied:
                    log.info(f"Applied to {jobID}")
                else:
                    log.info(f"Failed to apply to {jobID}")
                jobIDs[jobID] == applied

    def apply_to_job(self, jobID):
        # #self.avoid_lock() # annoying

        # get job page
        self.get_job_page(jobID)

        # let page load
        time.sleep(1)

        # get easy apply button
        button = self.get_easy_apply_button()

        # word filter to skip positions not wanted
        if button is not False:
            if any(word in self.browser.title for word in blackListTitles):
                log.info(
                    'skipping this application, a blacklisted keyword was found in the job position')
                string_easy = "* Contains blacklisted keyword"
                result = False
            else:
                string_easy = "* has Easy Apply Button"
                log.info("Clicking the EASY apply button")
                button.click()
                clicked = True
                time.sleep(1)
                self.fill_out_fields()
                result: bool = self.send_resume()
                if result:
                    string_easy = "*Applied: Sent Resume"
                else:
                    string_easy = "*Did not apply: Failed to send Resume"
        elif "You applied on" in self.browser.page_source:
            log.info("You have already applied to this position.")
            string_easy = "* Already Applied"
            result = False
        else:
            log.info("The Easy apply button does not exist.")
            string_easy = "* Doesn't have Easy Apply Button"
            result = False

        # position_number: str = str(count_job + jobs_per_page)
        log.info(f"\nPosition {jobID}:\n {
                 self.browser.title} \n {string_easy} \n")

        self.write_to_file(button, jobID, self.browser.title, result)
        return result

    def write_to_file(self, button, jobID, browserTitle, result) -> None:
        def re_extract(text, pattern):
            target = re.search(pattern, text)
            if target:
                target = target.group(1)
            return target

        timestamp: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attempted: bool = False if button == False else True
        job = re_extract(browserTitle.split(' | ')[0], r"\(?\d?\)?\s?(\w.*)")
        company = re_extract(browserTitle.split(' | ')[1], r"(\w.*)")

        toWrite: list = [timestamp, jobID, job, company, attempted, result]
        with open(self.filename, 'a+') as f:
            writer = csv.writer(f)
            writer.writerow(toWrite)

    def get_job_page(self, jobID):

        job: str = 'https://www.linkedin.com/jobs/view/' + str(jobID)
        self.browser.get(job)
        self.job_page = self.load_page(sleep=0.5)
        return self.job_page

    def get_easy_apply_button(self):
        EasyApplyButton = False
        try:
            buttons = self.get_elements("easy_apply_button")
            # buttons = self.browser.find_elements("xpath",
            #     '//button[contains(@class, "jobs-apply-button")]'
            # )
            for button in buttons:
                if "Easy Apply" in button.text:
                    EasyApplyButton = button
                    self.wait.until(
                        EC.element_to_be_clickable(EasyApplyButton))
                else:
                    log.debug("Easy Apply button not found")

        except Exception as e:
            print("Exception:", e)
            log.debug("Easy Apply button not found")

        return EasyApplyButton

    def fill_out_fields(self):
        fields = self.browser.find_elements(
            By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")
        for field in fields:

            if "Mobile phone number" in field.text:
                field_input = field.find_element(By.TAG_NAME, "input")
                field_input.clear()
                field_input.send_keys(self.phone_number)

        return

    def get_elements(self, type) -> list:
        elements = []
        element = self.locator[type]
        if self.is_present(element):
            elements = self.browser.find_elements(element[0], element[1])
        return elements

    def is_present(self, locator):
        return len(self.browser.find_elements(locator[0],
                                              locator[1])) > 0

    def send_resume(self) -> bool:
        def is_present(button_locator) -> bool:
            return len(self.browser.find_elements(button_locator[0],
                                                  button_locator[1])) > 0

        try:
            # time.sleep(random.uniform(1.5, 2.5))
            next_locator = (By.CSS_SELECTOR,
                            "button[aria-label='Continue to next step']")
            review_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Review your application']")
            submit_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Submit application']")
            error_locator = (By.CLASS_NAME, "artdeco-inline-feedback__message")
            upload_resume_locator = (
                By.XPATH, '//span[text()="Upload resume"]')
            upload_cv_locator = (
                By.XPATH, '//span[text()="Upload cover letter"]')
            # WebElement upload_locator = self.browser.find_element(By.NAME, "file")
            follow_locator = (
                By.CSS_SELECTOR, "label[for='follow-company-checkbox']")

            submitted = False
            loop = 0
            while loop < 2:
                time.sleep(1)
                # Upload resume
                if is_present(upload_resume_locator):
                    # upload_locator = self.browser.find_element(By.NAME, "file")
                    try:
                        resume_locator = self.browser.find_element(
                            By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]")
                        resume = self.uploads["Resume"]
                        resume_locator.send_keys(resume)
                    except Exception as e:
                        log.error(e)
                        log.error("Resume upload failed")
                        log.debug("Resume: " + resume)
                        log.debug("Resume Locator: " + str(resume_locator))
                # Upload cover letter if possible
                if is_present(upload_cv_locator):
                    cv = self.uploads["Cover Letter"]
                    cv_locator = self.browser.find_element(
                        By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]")
                    cv_locator.send_keys(cv)

                    # time.sleep(random.uniform(4.5, 6.5))
                elif len(self.get_elements("follow")) > 0:
                    elements = self.get_elements("follow")
                    for element in elements:
                        button = self.wait.until(
                            EC.element_to_be_clickable(element))
                        button.click()

                if len(self.get_elements("submit")) > 0:
                    elements = self.get_elements("submit")
                    for element in elements:
                        button = self.wait.until(
                            EC.element_to_be_clickable(element))
                        button.click()
                        log.info("Application Submitted")
                        submitted = True
                        break

                elif len(self.get_elements("error")) > 0:
                    elements = self.get_elements("error")
                    if "application was sent" in self.browser.page_source:
                        log.info("Application Submitted")
                        submitted = True
                        break
                    elif len(elements) > 0:
                        while len(elements) > 0:
                            log.info(
                                "Please answer the questions, waiting 5 seconds...")
                            time.sleep(5)
                            elements = self.get_elements("error")

                            for element in elements:
                                self.process_questions()

                            if "application was sent" in self.browser.page_source:
                                log.info("Application Submitted")
                                submitted = True
                                break
                            elif is_present(self.locator["easy_apply_button"]):
                                log.info("Skipping application")
                                submitted = False
                                break
                        continue
                        # add explicit wait

                    else:
                        log.info("Application not submitted")
                        time.sleep(2)
                        break
                    # self.process_questions()

                elif len(self.get_elements("next")) > 0:
                    elements = self.get_elements("next")
                    for element in elements:
                        button = self.wait.until(
                            EC.element_to_be_clickable(element))
                        button.click()

                elif len(self.get_elements("review")) > 0:
                    elements = self.get_elements("review")
                    for element in elements:
                        button = self.wait.until(
                            EC.element_to_be_clickable(element))
                        button.click()

                elif len(self.get_elements("follow")) > 0:
                    elements = self.get_elements("follow")
                    for element in elements:
                        button = self.wait.until(
                            EC.element_to_be_clickable(element))
                        button.click()

        except Exception as e:
            log.error(e)
            log.error("cannot apply to this job")
            pass
            # raise (e)

        return submitted

    def process_questions(self):
        time.sleep(1)
        form_fields = self.browser.find_elements(
            By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")

        for field in form_fields:
            try:
                # Get the question text and clean it
                question_element = field.find_element(By.TAG_NAME, "label")
                question = question_element.text.strip().lower()
                if not question:  # Skip empty fields
                    continue

                log.info(f"Found question: {question}")

                # Check if we have an existing answer
                answer = None
                for stored_question, stored_answer in self.answers.items():
                    # Use partial matching to handle slight variations in questions
                    if stored_question and stored_question.lower() in question:
                        answer = stored_answer
                        log.info(f"Found stored answer for question: {
                                 question} -> {answer}")
                        break

                # If no stored answer found, get a new one
                if answer is None:
                    answer = self.ans_question(question)
                    log.info(f"Generated new answer for question: {
                             question} -> {answer}")

                # Now handle different input types based on field inspection
                field_html = field.get_attribute("outerHTML")

                # Radio buttons
                if 'type="radio"' in field_html:
                    radio_inputs = field.find_elements(
                        By.CSS_SELECTOR, "input[type='radio']")
                    for radio in radio_inputs:
                        try:
                            label = self.browser.find_element(
                                By.CSS_SELECTOR, f"label[for='{radio.get_attribute('id')}']")
                            if str(answer).lower() in label.text.lower():
                                self.browser.execute_script(
                                    "arguments[0].click();", radio)
                                log.info(f"Clicked radio button: {label.text}")
                                break
                        except Exception as e:
                            log.error(f"Error with radio button: {str(e)}")

                # Dropdowns
                elif 'select' in field_html:
                    try:
                        select_element = field.find_element(
                            By.TAG_NAME, "select")
                        options = select_element.find_elements(
                            By.TAG_NAME, "option")
                        for option in options:
                            if str(answer).lower() in option.text.lower():
                                option.click()
                                log.info(f"Selected dropdown option: {
                                         option.text}")
                                break
                    except Exception as e:
                        log.error(f"Error with dropdown: {str(e)}")

                # Textboxes
                else:
                    try:
                        input_field = field.find_element(By.TAG_NAME, "input")
                        input_field.clear()
                        input_field.send_keys(str(answer))
                        log.info(f"Filled text input with: {answer}")
                    except Exception as e:
                        log.error(f"Error with text input: {str(e)}")

                # Save to answers dictionary and CSV right after successful input
                if question not in self.answers:
                    self.answers[question] = answer
                    try:
                        new_data = pd.DataFrame(
                            {"Question": [question], "Answer": [answer]})
                        if os.path.exists(self.qa_file):
                            new_data.to_csv(
                                self.qa_file, mode='a', header=False, index=False, encoding='utf-8')
                        else:
                            new_data.to_csv(
                                self.qa_file, index=False, encoding='utf-8')
                        log.info(f"Saved new QA pair to file: {
                                 question} -> {answer}")
                    except Exception as e:
                        log.error(f"Error saving to QA file: {str(e)}")

            except Exception as e:
                log.error(f"Error processing field: {str(e)}")
                continue

    def ans_question(self, question):
        # First check if we already have an answer stored
        question = question.lower().strip()

        # Define patterns for common questions
        patterns = {
            r'experience|years': "4 years",
            r'sponsor|visa': "No",
            r'salary|compensation|pay': self.salary,
            r'rate|hourly': self.rate,
            r'do you|have you|can you|are you|willing|available|eligible|able to': "Yes",
            r'uk citizen|us citizen|authorized|legal|right to work': "Yes",
            r'gender': "Male",
            r'race|lgbtq|ethnicity|nationality|veteran|diversity': "Prefer not to say",
            r'govt|government|clearance': "No",
            r'phone|mobile|contact': self.phone_number,
            r'first name': "Aakash",
            r'last name': "Priyadarshi",
            r'full name|name': "Aakash Priyadarshi",
            r'notice period|notice': "4 weeks",
            r'remote|work from home': "Yes",
            r'linkedin': "https://www.linkedin.com/in/aakash-priyadarshi",
            r'website|portfolio': "https://github.com/aakash",
            r'commute|relocate|travel': "Yes",
            r'education|degree|qualification': "Bachelor's in Computer Science",
            r'python|javascript|react|node': "Yes, proficient",
            r'language|english': "Fluent"
        }

        # Try to match the question with patterns
        for pattern, ans in patterns.items():
            if re.search(pattern, question):
                log.info(f"Found pattern match: {pattern} -> {ans}")
                return ans

        # If no pattern matched, ask for input
        log.info(f"No automatic answer for: {question}")
        answer = input(f"Please provide answer for: {question}\n")

        return answer

    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script(
                "window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 500
            time.sleep(sleep)

        if sleep != 1:
            self.browser.execute_script("window.scrollTo(0,0);")
            time.sleep(sleep)

        page = BeautifulSoup(self.browser.page_source, "lxml")
        return page

    def avoid_lock(self) -> None:
        x, _ = pyautogui.position()
        pyautogui.moveTo(x + 200, pyautogui.position().y, duration=1.0)
        pyautogui.moveTo(x, pyautogui.position().y, duration=0.5)
        pyautogui.keyDown('ctrl')
        pyautogui.press('esc')
        pyautogui.keyUp('ctrl')
        time.sleep(0.5)
        pyautogui.press('esc')

    def next_jobs_page(self, position, location, jobs_per_page, experience_level=[]):
        # Construct the experience level part of the URL
        experience_level_str = ",".join(
            map(str, experience_level)) if experience_level else ""
        experience_level_param = f"&f_E={
            experience_level_str}" if experience_level_str else ""
        self.browser.get(
            # URL for jobs page
            "https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords=" +
            position + location + "&start=" + str(jobs_per_page) + experience_level_param)
        # self.avoid_lock()
        log.info("Loading next job page?")
        self.load_page()
        return (self.browser, jobs_per_page)

    # def finish_apply(self) -> None:
    #     self.browser.close()


if __name__ == '__main__':

    with open("config.yaml", 'r') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise exc

    assert len(parameters['positions']) > 0
    assert len(parameters['locations']) > 0
    assert parameters['username'] is not None
    assert parameters['password'] is not None
    assert parameters['phone_number'] is not None

    if 'uploads' in parameters.keys() and type(parameters['uploads']) == list:
        raise Exception("uploads read from the config file appear to be in list format" +
                        " while should be dict. Try removing '-' from line containing" +
                        " filename & path")

    log.info({k: parameters[k] for k in parameters.keys()
             if k not in ['username', 'password']})

    output_filename: list = [f for f in parameters.get(
        'output_filename', ['output.csv']) if f is not None]
    output_filename: list = output_filename[0] if len(
        output_filename) > 0 else 'output.csv'
    blacklist = parameters.get('blacklist', [])
    blackListTitles = parameters.get('blackListTitles', [])

    uploads = {} if parameters.get(
        'uploads', {}) is None else parameters.get('uploads', {})
    for key in uploads.keys():
        assert uploads[key] is not None

    locations: list = [l for l in parameters['locations'] if l is not None]
    positions: list = [p for p in parameters['positions'] if p is not None]

    bot = EasyApplyBot(parameters['username'],
                       parameters['password'],
                       parameters['phone_number'],
                       parameters['salary'],
                       parameters['rate'],
                       uploads=uploads,
                       filename=output_filename,
                       blacklist=blacklist,
                       blackListTitles=blackListTitles,
                       experience_level=parameters.get('experience_level', [])
                       )
    bot.start_apply(positions, locations)
