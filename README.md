# CraDocs: Secure Temporary Document Vault

<img width="1897" height="1079" alt="Screenshot 2026-10-22 112420" src="https://github.com/user-attachments/assets/0642ba42-4226-42bf-ad8b-e68fab6e8d45" />


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
<img width="1896" height="1079" alt="Screenshot 2026-10-22 112559" src="https://github.com/user-attachments/assets/4f82b825-c05d-4efa-a7e0-7e1191be7269" />
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
<img width="1900" height="1079" alt="Screenshot 2026-10-22 112504" src="https://github.com/user-attachments/assets/d041f320-e16f-4e49-9c63-318cdb0394fd" />
## Clean up after your demo
Delete the CloudFormation stack (empty the S3 bucket first) and terminate the
EC2 instance, so nothing keeps billing.




<img width="1898" height="1079" alt="Screenshot 2026-10-22 112244" src="https://github.com/user-attachments/assets/0d25e531-9ddc-45eb-a7d8-22a8818cd7ad" />


