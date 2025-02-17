from flask import Flask, redirect, url_for, session, request
from werkzeug.middleware.proxy_fix import ProxyFix
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pathlib import Path
import argparse
import logging
import json
import os
import pdb
import requests
import time
import webbrowser


def setup_logger():
    logger = logging.getLogger('FlaskServer')
    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler('archive.log')

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

def parse_em_argggs_matey():
    parser = argparse.ArgumentParser(description='Citation Processor: Run Flask Server behind ngrok proxy for Google OAuth then process Google Doc')
    parser.add_argument(
        '--ngrok_url',
        type=str,
        required=True,
        help='The ngrok URL'
    )
    parser.add_argument(
        '--document_id',
        type=str,
        required=True,
        help='The id of the Google Document to be processed'
    )
    args = parser.parse_args()
    return args
class FlaskServer:
    def __init__(self, ngrok_url, logger):
        self.logger = logger
        self.ngrok_url = ngrok_url
        self.app = Flask(__name__)
        self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_proto=1, x_host=1) # needed to have Flask respect X-Forwarded-Proto (otherwise http)
        self.app.secret_key = 'a-very-secret-development-key'
        self.CLIENT_SECRETS_FILE = 'credentials.json'
        self.SCOPES = ['https://www.googleapis.com/auth/documents',
                'https://www.googleapis.com/auth/documents.readonly',
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/drive.file'
                ]
        self.setup_routes()
    
    def run(self):
        self.app.run(host='0.0.0.0', port=5001, debug=True)

    def setup_routes(self):
        flow = Flow.from_client_secrets_file(
                self.CLIENT_SECRETS_FILE,
                scopes=self.SCOPES,
                redirect_uri=f'{self.ngrok_url}/callback'
            )

        @self.app.route('/')
        def index():
            return '', 200

        @self.app.route('/auth')
        def auth():
            self.logger.info('auth/: going through auth flow')
            auth_url, state = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
            session['state'] = state
            self.logger.info(f'auth/: redirecting to {auth_url}')
            return redirect(auth_url)

        @self.app.route('/callback')
        def callback():
            # Verify the state to protect against CSRF attacks
            if 'state' not in session or session['state'] != request.args.get('state'):
                error_message = 'State mismatch. Potential security risk.'
                self.logger.error(f'/callback: {error_message}')
                return error_message, 400

            self.logger.error(f'/callback: fetching token')
            flow.fetch_token(authorization_response=request.url)
            self.logger.error(f'/callback: fetched token')
            credentials = flow.credentials

            session['credentials'] = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }

            url = url_for('profile')
            self.logger.info(f'/callback: redirecting to {url}')
            return redirect(url)

        @self.app.route('/profile')
        def profile():
            if 'credentials' not in session:
                self.logger.info('/profile: redirecting to /auth')
                return redirect('/auth')
            credentials = Credentials(**session['credentials'])
            userinfo_endpoint = 'https://openidconnect.googleapis.com/v1/userinfo'
            response = requests.get(userinfo_endpoint, headers={
                'Authorization': f'Bearer {credentials.token}'
            })
            user_info = response.json()

            try:
                return f"""
                <h1>User Profile</h1>
                <p><strong>Name:</strong> {user_info['name']}</p>
                <p><strong>Email:</strong> {user_info['email']}</p>
                <p><img src="{user_info['picture']}" alt="Profile Picture" style="border-radius: 50%;"></p>
                <a href="/logout">Logout</a>
                """
            except Exception as e:
                print(e)
                return str(user_info)

        @self.app.route('/logout')
        def logout():
            self.logger.info('/logout: logging out')
            session.clear()
            return redirect('/')

        @self.app.route('/get_doc/<doc_id>')
        def get_doc(doc_id):
            if 'credentials' not in session:
                self.logger.info('/get_doc: redirecting to /auth')
                return redirect('/auth')
            credentials = Credentials(**session['credentials'])
            service = build('docs', 'v1', credentials=credentials)
            self.logger.info('get_doc/: retrieving doc')
            doc = service.documents().get(documentId=doc_id).execute()
            self.logger.info(f'get_doc/: writing: {doc_id}.json')
            directory_path = Path(f"{doc_id}")
            directory_path.mkdir(parents=True, exist_ok=True)
            f = open(f'{doc_id}/doc.json', 'w+')
            f.write(json.dumps(doc))
            f.close()

            self.logger.info(f'get_doc/: written: {doc_id}.json')
            return doc

        @self.app.route('/archive_doc/<doc_id>')
        def archive_doc_urls(doc_id):
            f = open(f'{doc_id}/doc.json', 'r')
            data = f.read()
            f.close()
            data = json.loads(data)

            urls = []
            skipped_urls = []
            blocked_urls = []
            failed_archived = []
            archive_mapping = {}
            url_job_id_mapping = {}
            base_url = 'https://web.archive.org'

            # Parse URLs
            for footnotes in data['footnotes']:
                for c in data['footnotes'][footnotes]['content']:
                    for element in c['paragraph']['elements']:
                        try:
                            url = element['textRun']['textStyle']['link']['url']
                            if url not in urls:
                                urls.append(url)
                        # This is okay, most of the elements do NOT have links, logging the misses isn't valuable
                        except KeyError as e:
                            pass
                        except Exception as e:
                            self.logger.error(f'Error processing {element}')

            # Archive request
            headers = {'Authorization': f'LOW {os.environ["SPN_KEY"]}:{os.environ["SPN_SECRET_KEY"]}','Accept': 'application/json'}
            blocked_text = "This URL is in the Save Page Now service block list and cannot be captured."
            captured_text = "This URL has been already captured"

            skipped_domains = [
                'docs.google.com',
                'drive.google.com',
                'facebook.com',
                'instagram.com',
                'linkedin.com',
                'maps.app.goo',
                'web.archive.org',
                'x.com',
                'youtu.be',
                'youtube.com',
            ]
            for url in urls:
                if any(domain in url for domain in skipped_domains):
                    skipped_urls.append(url)
                    self.logger.info(f'Skipping archive job request for {url}: Facebook or archive url')
                    continue

                retries = 3
                success = False
                for attempt in range(1, retries + 1):
                    try:
                        response = requests.post('https://web.archive.org/save', headers=headers, data={'url':url})
                        if response.status_code == 200:
                            response = json.loads(response.text)
                            
                            if 'message' in response and (blocked_text in response['message'] or captured_text in response['message']):
                                self.logger.warning(f"{url} blocked")
                                blocked_urls.append(url)
                                success = True
                                break
                            if 'job_id' not in response:
                                self.logger.warning(response.text)
                            else:
                                job_id = response['job_id']
                                url_job_id_mapping[url] = job_id
                        else:
                            raise Exception
                        self.logger.info(f'Archive job request sent for url: {url} with job_id: {job_id}')
                        success = True
                        break
                    except Exception as e:
                        self.logger.error(f'Attempt {attempt} failed for url {url}: {e}')
                        if attempt < retries:
                            seconds = 13
                            self.logger.info(f'Retrying in {seconds} seconds... (Attempt {attempt + 1}/{retries})')
                            time.sleep(seconds)
                        else:
                            self.logger.error(f'Failed to send archive job request for {url} after {retries} attempts')
                            skipped_urls.append(url)

                # Authenticated users can request a max of 5 saves per minute, this is slightly conservative
                time.sleep(13)
                if not success:
                    self.logger.error(f'Failed to send archive job request for {url}')
                    continue

            f = open(f"{doc_id}/new_mapping_requests.json", "w+")
            f.write(json.dumps(url_job_id_mapping))
            f.close()
            self.logger.info(f'Wrote {doc_id}/new_mapping_requests.json')

            f = open(f'{doc_id}/blocked.json', 'w+')
            f.write(json.dumps(blocked_urls))
            f.close()
            self.logger.info(f'Wrote {doc_id}/blocked.json')

            f = open(f'{doc_id}/skipped.json', 'w+')
            f.write(json.dumps(skipped_urls))
            f.close()
            self.logger.info(f'Wrote {doc_id}/skipped.json')

            # Retrieve job archival request status
            for url in url_job_id_mapping:
                get_url = f'https://web.archive.org/save/status/{url_job_id_mapping[url]}'
                self.logger.info(f'Getting {get_url}')
                response = requests.get(get_url, headers=headers)
                if response.status_code == 200:
                    data = json.loads(response.text)
                    if data['status'] == "success":
                        archive_url = f'{base_url}/{url}'
                        archive_mapping[url] = archive_url
                        self.logger.info(f'Successful archival of {url}: {archive_url}')
                else:
                    failed_archived.append(url)
                    self.logger.error(f'Failed archival of {url}')
                time.sleep(30)

            f = open(f'{doc_id}/url_mapping.json', 'w+')
            f.write(json.dumps(archive_mapping))
            f.close()

            f = open(f'{doc_id}/failed_archived.json', 'w+')
            f.write(json.dumps(failed_archived))
            f.close()
            
            return_dict = {
                "archive_mapping": archive_mapping,
                "blocked_urls": blocked_urls,
                "skipped_urls": skipped_urls,
                "failed_archive": failed_archived,
            }

            return return_dict

        @self.app.route('/get_archived/<doc_id>')
        def get_doc_mapping(doc_id):
            data = "File not found, check local file system"
            try:
                f = open(f'{doc_id}/url_mapping.json', 'r')
                data = json.loads(f.read())
                f.close()
            except:
                self.logger.error(data)
            return data

if __name__ == '__main__':
    logger = setup_logger()
    args = parse_em_argggs_matey()
    app = FlaskServer(ngrok_url=args.ngrok_url, logger=logger)
    app.run()

    # f = open(f"{args.document_id}/url_mapping.json", 'r')
    # data = json.loads(f.read())
    # f.close()
    # for i, k in enumerate(data):
    #     time.sleep(1)
    #     webbrowser.open_new_tab(data[k])
    #     if i % 20 == 0:
    #         pdb.set_trace()