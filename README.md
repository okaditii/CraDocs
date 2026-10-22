# CraDocs: Secure Temporary Document Vault

Upload documents, share with specific users, set an access window and download
limit, and have them auto-deleted. "Important" documents are password-protected
and never auto-deleted.

## Run locally (free, no AWS needed)

Double-click `run.bat`, or:

    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000
    python cleanup.py        # run the expiry job by hand
    python test_cradocs.py   # run the tests

Data is stored in `./data` (db.json + files/). Delete that folder to reset.

## Features
- Accounts with per-user default auto-delete time
- Share with named users only, with a start time, expiry and download limit
- Owner can revoke users, change limits, reset expiry, or delete early
- Important documents: no expiry, password required to open/change/delete
- Expired documents are denied instantly, then physically deleted by the cleanup job
- CSRF protection, hashed passwords, 10 MB upload cap

## Deploy on AWS (free tier)

Set a zero-spend budget alert first.

1. **One click infra**: CloudFormation -> Create stack -> upload `template.yaml`
   (region of your choice). It creates the private S3 bucket, both DynamoDB
   tables, the cleanup Lambda, the 1-minute EventBridge backup schedule (the running
   app itself deletes each document the moment it expires) and the EC2
   instance profile. Note the `BucketName` output.
2. **EC2**: launch a free-tier-eligible `t3.micro`/`t2.micro` (Amazon Linux),
   attach the `InstanceProfile` from the stack, open port 80/8000 in the
   security group, then on the instance:

       sudo dnf install -y python3-pip git
       # copy this folder over (git clone or scp), then:
       pip3 install -r requirements.txt gunicorn
       export CRADOCS_MODE=aws CRADOCS_BUCKET=<BucketName> SECRET_KEY=<long random>
       gunicorn -b 0.0.0.0:8000 app:app

3. HTTPS: for anything with real data, put nginx + Let's Encrypt (or a free
   Cloudflare tunnel) in front. Don't send real Aadhaar data over plain HTTP.

## Clean up after your demo
Delete the CloudFormation stack (empty the S3 bucket first) and terminate the
EC2 instance, so nothing keeps billing.
