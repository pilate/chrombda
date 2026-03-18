# chrombda

AWS Lambda screenshot service. Takes a URL, screenshots it with headless Chrome via [cdipy](https://github.com/pilate/cdipy), saves the PNG to S3.

## Deploy

```bash
./deploy.sh dev
```

## Usage

Via the Lambda Function URL:

```bash
curl "https://<function-url>/?url=https://example.com"
```

Screenshots are stored in S3 at:
```
screenshots/<domain>/<url-hash>/<timestamp>.png
```

## Scheduled screenshots

```bash
./create-schedule.sh dev https://example.com 'rate(1 hour)'
./create-schedule.sh prod https://example.com 'cron(0 */6 * * ? *)'
```
