# Deploying the unified review suite to AWS

## Supplied course server

The supplied `README - AWS Server.docx` describes a shared EC2 server, per-app subdomains, Nginx/TLS, and possible app-level Touchstone/SAML. It explicitly limits that shared server to test deployments and says not to store sensitive student data there. Use empty workspaces and synthetic documents on that server. No SSH key or tutorial credential is needed to build this application package; none is included in its Docker image or ZIP.

## EC2 with Docker Compose

1. Run `python build_deploy_bundle.py` locally. Transfer `dist/design-review-suite.zip` to an authorized server and unzip it into a new application directory.
2. Install Docker with Compose on the server. Copy `.env.example` to `.env`. Generate an access code with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and put it in `.env` as `REVIEW_ACCESS_TOKEN`. Keep `.env` private to the deployment operator.
3. Set `REVIEW_PUBLIC_ORIGIN=https://your-app.example.edu` and `REVIEW_TRUST_PROXY=1`. Leave optional API keys/models blank until you need them. The origin must be the hostname users actually open.
4. Run `docker compose up -d --build`. The service is published only to `127.0.0.1:8080`. `curl http://127.0.0.1:8080/healthz` should return `{"service":"review-suite","status":"ok"}`.
5. Configure DNS and TLS for the chosen hostname. Insert `deploy/nginx.conf.example` into the existing HTTPS server block. Nginx must replace forwarded headers, preserve the public Host, and be the only route to the backend. Open HTTPS at the security group; keep port 8080 inaccessible externally.
6. Open the HTTPS application URL and enter the workspace access code. Verify each tab, a synthetic PDF upload, a synthetic ESDP inventory and restart persistence before allowing actual authorized use.

Waitress is the production WSGI server on both Windows and Linux. Its serving model follows the [Flask production deployment guidance](https://flask.palletsprojects.com/en/stable/deploying/waitress/). Proxy headers are opt-in and configured for one upstream, following [Flask ProxyFix guidance](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/). Do not expose the backend directly with trusted proxy mode enabled.

## Data and backups

Compose mounts the named `review-data` volume at `/data`. Container rebuilds preserve that volume. Do not run `docker compose down -v` unless permanently deleting its data is intended. Back up the entire volume, with the service stopped for a consistent snapshot. Restore ownership to container UID 10001. JSON exports alone are not full backups.

The image starts empty by design. Do not transfer the locally imported student reviews to the shared test server. For a separate institution-approved destination, migrate only authorized data into `/data/pdr` and `/data/cdr` with the service stopped. Files must be writable by UID 10001. Confirm retention, encryption, backups and access requirements for that destination.

## ECS/Fargate option

Build and push the same image to ECR, run it as an ECS service behind an HTTPS Application Load Balancer, and mount persistent storage at `/data`. AWS supports [ALB integration with ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-load-balancing.html) and [EFS volumes for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html). Set the access point's UID/GID to 10001 when using EFS. Inject access codes and optional model credentials through the deployment's secret manager, not Docker build arguments.

Keep desired count at one and prevent overlapping writers during deployments (for a single-task ECS rolling deployment, use minimum healthy percent 0 and maximum percent 100, accepting downtime). EFS does not make the JSON state multi-writer safe. Proxy scheme handling must match the actual ALB/proxy path; do not blindly trust forwarded headers from public clients.

For individual institutional identity, implement and validate OIDC/Cognito or app-level Touchstone/SAML. AWS provides [ALB authentication with Cognito or OIDC](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html). This suite currently provides only shared access-code authentication; it has no student-level authorization or permission-separated RAG corpus. Health checks intentionally expose only service status and require no access code.

## Operational checks

- Limit this storage implementation to one application process/replica.
- Keep backend traffic restricted to the trusted reverse proxy.
- Test secure login, logout, source-file access and CSRF rejection through HTTPS.
- Confirm uploads up to 20 MB work through proxy/body limits; application JSON limit is 30 MB for base64 overhead.
- Allow 240 seconds through the proxy for optional AI calls; ESDP allows one review at a time.
- Add infrastructure-level rate limiting before wider exposure; shared access codes provide no per-user audit history.
- Validate model behavior and rubrics independently before using feedback in course decisions.

No deployment, domain registration, institutional authentication registration or live model request is performed by the source package.
