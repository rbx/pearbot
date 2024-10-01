import json
import sys
import traceback
from flask import Flask, request, abort
from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()

try:
    from auth import verify_webhook_signature, get_installation_access_token
    from storage import get_or_create_session
    from agents import CodeReviewAgent
except EnvironmentError as e:
    print(f"Error: {e}")
    print("Please ensure all required environment variables are set in your .env file.")
    sys.exit(1)

app = Flask(__name__)
code_review_agent = CodeReviewAgent()

@app.route('/webhook', methods=['POST'])
def webhook():
    separator = "\n--------\n########\n--------"
    print("Webhook received")
    # print(f"Headers: {request.headers}{separator}")
    # print(f"Raw data: {request.data}{separator}")

    if not verify_webhook_signature(request):
        print("Webhook signature verification failed")
        abort(401)

    event = request.headers.get("X-GitHub-Event")
    payload = request.json

    print(f"Received event: {event}")
    # print(f"Payload: {json.dumps(payload, indent=2)}")

    if event == "pull_request":
        handle_pull_request(payload)
    elif event == "pull_request_review":
        handle_pull_request_review(payload)
    elif event == "issue_comment":
        handle_issue_comment(payload)

    return 'Webhook received', 200

def handle_pull_request(payload):
    action = payload["action"]
    pr = payload["pull_request"]
    repo = payload["repository"]
    installation_id = payload["installation"]["id"]

    session = get_or_create_session(pr['number'], repo['full_name'])
    session.add_message("system", f"Pull Request #{pr['number']} {action}: {pr['title']}")
    session.add_message("user", f"Description: {pr['body']}")

    print(f"\nPull Request #{pr['number']} {action}: {pr['title']}")
    print(f"Repository: {repo['full_name']}")
    print(f"Created by: {pr['user']['login']}")
    print(f"Description: {pr['body']}")

    access_token = get_installation_access_token(installation_id)
    g = Github(access_token)
    repo_obj = g.get_repo(repo['full_name'])
    pull_request = repo_obj.get_pull(pr['number'])

    diff_files = pull_request.get_files()

    print(f"Files changed in PR:")
    for file in diff_files:
        print(f"{file.filename} ({file.additions} additions, {file.deletions} deletions)")
        print(f"Changes:\n{file.changes}")
        print(f"Patch:\n{file.patch}")

    pr_data = {
        "title": pr['title'],
        "description": pr['body'],
        "files": [
            {
                "filename": file.filename,
                "status": file.status,
                "additions": file.additions,
                "deletions": file.deletions,
                "changes": file.changes,
                "patch": file.patch
            }
            for file in diff_files
        ]
    }

    file_comments = code_review_agent.analyze_pr(pr_data)

    try:
        print(f"\n\nReview comments:\n{file_comments}\n\n")
        pull_request.create_issue_comment(file_comments)
    except GithubException as e:
        print(f"GitHub API error: {e.status} - {e.data}")
    except Exception as e:
        print(f"Error posting review: {e}")
        print(f"Full exception: {traceback.format_exc()}")

    session.add_message("assistant", json.dumps(file_comments))

def handle_pull_request_review(payload):
    action = payload["action"]
    review = payload["review"]
    pr = payload["pull_request"]
    repo = payload["repository"]

    session = get_or_create_session(pr['number'], repo['full_name'])
    session.add_message("user", f"Review by {review['user']['login']}: {review['state']}\nComment: {review['body']}")

    print(f"\nPull Request #{pr['number']} Review {action}")
    print(f"Review by {review['user']['login']}: {review['state']}")
    print(f"Review comment: {review['body']}")

    # Here you would typically call your LLM to generate a response
    # For now, we'll just add a placeholder message
    # ai_response = "Thank you for your review. I'll take it into consideration."
    # session.add_message("assistant", ai_response)

def handle_issue_comment(payload):
    action = payload["action"]
    comment = payload["comment"]
    issue = payload["issue"]
    repo = payload["repository"]

    if "pull_request" in issue:
        session = get_or_create_session(issue['number'], repo['full_name'])
        session.add_message("user", f"Comment by {comment['user']['login']}: {comment['body']}")

        print(f"\nPull Request #{issue['number']} Comment {action}")
        print(f"Comment by {comment['user']['login']}: {comment['body']}")

        # Here you would typically call your LLM to generate a response
        # For now, we'll just add a placeholder message
        # ai_response = "Thank you for your comment. I'll take it into consideration."
        # session.add_message("assistant", ai_response)

if __name__ == "__main__":
    app.run(host="localhost", port=3000)
