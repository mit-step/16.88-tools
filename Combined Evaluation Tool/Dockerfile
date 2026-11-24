FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 REVIEW_HOST=0.0.0.0 PORT=8080 REVIEW_DATA_DIR=/data REVIEW_IMPORT_LEGACY=0
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
COPY review_suite ./review_suite
COPY ["PDR Evaluation Tool/pdr_tool.py", "PDR Evaluation Tool/workspace_app.py", "./PDR Evaluation Tool/"]
COPY ["PDR Evaluation Tool/web", "./PDR Evaluation Tool/web/"]
COPY ["CDR Evaluation Tool/cdr_tool.py", "CDR Evaluation Tool/workspace_app.py", "CDR Evaluation Tool/cdr_requirements.json", "CDR Evaluation Tool/CDR_gradingRubric.docx", "CDR Evaluation Tool/FinalProjectCDR_AssignmentDescription.docx.pdf", "./CDR Evaluation Tool/"]
COPY ["CDR Evaluation Tool/web", "./CDR Evaluation Tool/web/"]
COPY ["ESDP Evaluation Tool/esdp_review.py", "ESDP Evaluation Tool/rubric.json", "./ESDP Evaluation Tool/"]
COPY ["ESDP Evaluation Tool/web", "./ESDP Evaluation Tool/web/"]
RUN useradd --create-home --uid 10001 review && mkdir /data && chown review:review /data
USER review
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"
CMD ["python", "app.py"]
