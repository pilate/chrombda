# chrombda

AWS Lambda service that crawls a URL with headless Chrome via [cdipy](https://github.com/pilate/cdipy), capturing a screenshot and MHTML snapshot to S3.

## Deploy

```bash
./deploy.sh dev
```

## Usage

Via the Lambda Function URL:

```bash
curl "https://<function-url>/?url=https://example.com"
```

Data is stored in S3 at:
```
screenshots/<domain>/<url-hash>/<timestamp>.png
snapshots/<domain>/<url-hash>/<timestamp>.mhtml
```

## Scheduled crawls

```bash
./create-schedule.sh dev https://example.com 'rate(1 hour)'
./create-schedule.sh prod https://example.com 'cron(0 */6 * * ? *)'
```
