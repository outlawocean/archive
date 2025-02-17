# Google Docs Citations Archive Tool
There are several components to archiving Google Docs Citations

## The Flask Server
Requirements: Google OAuth credentials, ngrok<br>
Params: `--ngrok_url`, `--document_id`<br>
Purpose:
- Grab Google Doc URLs from footnotes. Google Documents API requires OAuth2, so this handles that, though you will need to generate credentials in your Google Developers account. Alternatively, you can also use the [User Interface](https://developers.google.com/docs/api/reference/rest/v1/documents/get) and this may be more convenient for one time use.
- Archive pages using SPN2 API: (1) Request archive (which returns job id) (2) Check on status of jobs (if successful, updates mapping) -- This process takes time -- authorized users can send a max of 5 requests per minute, so we conservatively sleep for 13 seconds between requests<br>

Use:
- Because OAuth2 is required, you'll need a public URL. You can use `ngrok` to expose your local Flask server: `ngrok http --domain=select-subtly-bass.ngrok-free.app 5001`
- GET `/get_doc/<doc_id>` to save the Google Document as JSON locally as `<doc_id>.json`
- GET `/archive_doc/<doc_id>` to hit the SPN2 API and archive the footnote citation URLs. The SPN2 API is finnicky, the output of this endpoint will return: (1) A mapping of successes -- url to archive url, (2) blocked urls (SPN2 blocks some pages) (3) skipped urls (facebook, instagram, twitter/x, linkedin), and (4) failed archives. These will also be saved to your local file system. SPN2 API sometimes returns 'successes' when they are indeed not (especially for Google Docs/Drive and YouTube pages I've found), so some manual verification may be needed.
- GET /get_archived/<doc_id> to return the mapping of successes
- `tail -f <log>` to keep track of the status of archives

## Apps Scripts
This is saved as `app_script.js`. Copy the mapping of successes to the mapping var, then run the script with the proper document id in [Apps Scripts](script.google.com/home/projects)

This will update the doc with (Archive) highlighted in green for those that are successful, and (Archive) highlighted in red which need filling in (failed to archive)

### Improvements
If this can be consolidated into App Scripts entirely, this would save the OAuth headache.

https://select-subtly-bass.ngrok-free.app/get_doc/12p4Par0B4LimM9-mmMSb0kzMV67TUBSYEzo5kxXO7Sg