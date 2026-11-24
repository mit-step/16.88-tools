"""Create a source-only AWS upload ZIP from an explicit allowlist."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = ['.gitignore', 'app.py', 'requirements.txt', 'Dockerfile', '.dockerignore', 'compose.yaml',
         '.env.example', 'README.md', 'Start Review Suite.cmd', 'build_deploy_bundle.py',
         'deploy/nginx.conf.example', 'deploy/AWS.md', 'review_suite/__init__.py',
         'review_suite/modules.py', 'review_suite/app.py', 'review_suite/assistant.py',
         'PDR Evaluation Tool/pdr_tool.py', 'PDR Evaluation Tool/workspace_app.py',
         'CDR Evaluation Tool/cdr_tool.py', 'CDR Evaluation Tool/workspace_app.py',
         'CDR Evaluation Tool/cdr_requirements.json', 'CDR Evaluation Tool/CDR_gradingRubric.docx',
         'CDR Evaluation Tool/FinalProjectCDR_AssignmentDescription.docx.pdf',
         'ESDP Evaluation Tool/esdp_review.py', 'ESDP Evaluation Tool/rubric.json']
for folder in ['review_suite/web', 'PDR Evaluation Tool/web', 'CDR Evaluation Tool/web', 'ESDP Evaluation Tool/web']:
    FILES.extend(f'{folder}/{name}' for name in (
        ['index.html','suite.css','suite.js','login.html'] if folder=='review_suite/web' else ['index.html','style.css','app.js']))

if __name__ == '__main__':
    destination = ROOT / 'dist' / 'design-review-suite.zip'
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as bundle:
        for filename in FILES:
            bundle.write(ROOT / filename, filename)
    print(destination)
    print('SHA256: ' + hashlib.sha256(destination.read_bytes()).hexdigest())
    print(f'{len(FILES)} application files; no reviews, workspace data, keys, or environment secrets.')
