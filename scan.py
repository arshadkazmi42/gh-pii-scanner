from multiprocessing.pool import ThreadPool as Pool

import re
import requests
import base64
import json
import sys
import time


EMAIL_REGEX = r'[-a-zA-Z\._]+[@](\w|\_|\-|\.)+[.]\w{2,3}'
PHONE_REGEX = r'(\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4,5}'


REQUEST_TIMEOUT = 40
GITHUB_SEARCH_API = 'https://api.github.com/search/code?o=desc&q='
START_PAGE_NUMBER = 1
SEARCH_QUERY = '"{}"+"email"+"phone"+NOT+extension%3Amd+NOT+extension%3Atxt+NOT+extension%3Ahtml+NOT+extension%3Aini+NOT+extension%3Aaspx+NOT+extension%3Amarkdown+NOT+extension%3Agemspec+NOT+extension%3Ashtml+NOT+extension%3Arst+NOT+extension%3Acsv+NOT+extension%3Ac+NOT+extension%3Acpp+NOT+extension%3Ah&type=Code&page='
IGNORE_EMAILS = ['legal', 'support', 'help', 'sales', 'feedback', 'enquiry', 'contact', 'privacy', 'selfservice', 'info@', 'john.doe', '.com@', 'test@', 'test.com', 'email.com', 'resellers@', '@yourcompany.com', 'resellers', 'example.com', '@domain.com', 'copyright@']
IGNORE_FILES = ['package.json', 'AUTHORS', 'change-log', 'setup.py', 'CONTRIBUTORS', 'ChangeLog', 'composer.json', 'pypi_packages', 'commits.json', 'AllVideoPocsFromHackerOne', '.cache.json', 'bugbounty', '.svn', 'inmotionhosting.com']
GH_RESULTS_PER_PAGE = 30
GH_MAX_PAGES = 34
MAX_THREADS = 5 
GH_TOKEN = None
DEBUG = False



# HELPER FUNCTIONS

def _print(text):
    # TODO Add debug / verbose flag / accept from arg
    if DEBUG:
        print(text)

def _get_url(domain):
    searchQuery = SEARCH_QUERY.format(domain)
    _print(searchQuery)
    return f'{GITHUB_SEARCH_API}{searchQuery}'

def _get_domain():
    args = sys.argv

    _print(args)
    _print(len(args))

    if len(args) < 2:
        _print('Missing domain')
        return

    return args[1]

def _get_gh_token():
    args = sys.argv

    _print(args)
    _print(len(args))

    if len(args) < 3:
        _print('Missing token')
        return

    return args[2]

def _check_rate_limit(response):

    if response.status_code == 403:

        if 'X-RateLimit-Remaining' in response.headers:
            limit_remaining = int(response.headers['X-RateLimit-Remaining'])
            print(f'Rate limit remaining {limit_remaining}')

            if limit_remaining > 0:
                return True

        if 'X-RateLimit-Reset' in response.headers:
            reset_time = int(response.headers['X-RateLimit-Reset'])
            current_time = int(time.time())
            sleep_time = reset_time - current_time + 1
            print(f'\n\nGitHub Search API rate limit reached. Sleeping for {sleep_time} seconds.\n\n')
            time.sleep(sleep_time)
            return True
    
    return False


def _get_url_result(url, token):

    try:
        headers = {}    

        if not token and GH_TOKEN:
            token = GH_TOKEN

        if token:
            headers['Authorization'] = f'token {token}'

        _print(headers)

        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        # if rate limit reached
        # Check and wait for x seconds
        if response.status_code == 403:
            if _check_rate_limit(response):
                response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f'\nFailed with error code {response.status_code}\n')
            print(response.text)
            return {}
            
        return response.json()
    except Exception as e:
        print(e)
        return None

def _get_total_pages(url, gh_token):

    result = _get_url_result(f'{url}{START_PAGE_NUMBER}', gh_token)

    total_count = 1
    if result and 'total_count' in result:
        total_count = result['total_count']

    if total_count > GH_RESULTS_PER_PAGE:
        return int(total_count / GH_RESULTS_PER_PAGE) + 1

    # If total results are less than the total results in one page
    # Return 2, since page_numbers starts with 1.
    # So it needs to do 1 iteration
    return 2


def _decode_base_64(text): 
    try:
        return base64.b64decode(text).decode("utf-8") 
    except Exception as e:
        print(e)
        return None


def _write_to_file(line):
    # filename = _get_github_username()
    filename = _get_domain()
    f = open(f'{filename}.txt', 'a')
    f.write(f'{line}\n')  # python will convert \n to os.linesep
    f.close()


def _extract_emails(text):

    matches = []

    for iterator in re.finditer(EMAIL_REGEX, text):
        matches.append(iterator.group())

    return matches


def _search_content(url, content):
    try:

        if any(value in url for value in IGNORE_FILES):
            return False

        _print(content)
        result = _decode_base_64(content)
        _print(str(result))

        print(f'Searching in {url}')

        matches = _extract_emails(result)

        if len(matches) == 0:
            return False

        domain = _get_domain()

        found_email_line = ''

        for match in matches:

            if domain not in match:
                continue

            if any(value in match for value in IGNORE_EMAILS):
                continue
            
            found_email_line = f'{found_email_line}Found Email: {match}\n'

        if len(found_email_line) > 0:

            print_line = f'\n\nFound in {url}'
            print(print_line)
            _write_to_file(print_line)

            _write_to_file(found_email_line)
            print(found_email_line)
            
            print('\n\n')

    except Exception as e:
        print(e)

def _is_archived(item, gh_token):
    if 'repository' in item and 'url' in item['repository']:
        repo_url = item['repository']['url']

        repo = _get_url_result(repo_url, gh_token)

        if repo and 'archived' in repo:
            _print(f'{repo["name"]} => Archieved => {str(repo["archived"])}')
            return repo['archived']

        return False

    return False

def _get_and_search_content(item, gh_token):

    if _is_archived(item, gh_token):
        return

    if 'url' in item:

        result = _get_url_result(item['url'], gh_token)
        html_url = item['html_url']

        if result and 'content' in result:
            _search_content(html_url, result['content'])


def process_page(url, gh_token):

    result = _get_url_result(url, gh_token)
    
    if result and 'items' in result:

        pool = Pool(MAX_THREADS)
        
        items = result['items']
        for item in items:
            pool.apply_async(_get_and_search_content, (item,gh_token,))

        pool.daemon = True
        pool.close()
        pool.join()


# MAIN CODE

gh_token = _get_gh_token()

domain = _get_domain()

url = _get_url(domain)

total_urls = 0
total_pages = _get_total_pages(url, gh_token)
if total_pages > GH_MAX_PAGES:
    total_pages = GH_MAX_PAGES

for page_number in range(START_PAGE_NUMBER, total_pages):
    
    _print(page_number)
    print(f'Processing: {url}{page_number}')

    process_page(f'{url}{page_number}',gh_token)

