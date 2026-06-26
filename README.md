# mimo-farmer

MiMo account creator CLI.

Simple flow:

```powershell
python -m mimo_farmer create --referral CODE --count N
```

## Features

- Create MiMo accounts with referral code.
- Set account quantity with `--count`.
- Automatic OTP polling from generator.email.
- reCAPTCHA handling through existing pipeline.
- Xiaomi signup, terms handling, balance check, and API key extraction.
- Batch TXT output in `accounts/`.

## Requirements

- Python 3.12 recommended.
- Google Chrome / supported browser environment.
- Project dependencies installed.

Example Python command:

```powershell
python
```

## Installation

```powershell
git clone https://github.com/rapoii/mimo-farmer.git
cd mimo-farmer
pip install -e .
```

If running on Rafi's local machine, clear `PYTHONPATH` first:

```powershell
$env:PYTHONPATH=""
```

## Usage

### Show help

```powershell
python -m mimo_farmer --help
```

### Create accounts

```powershell
python -m mimo_farmer create --referral ABC123 --count 5
```

Short version:

```powershell
python -m mimo_farmer create -r ABC123 -n 5
```

If `--referral` or `--count` is not provided, CLI asks interactively.

## Commands

```text
mimo create --referral CODE --count N
```

| Option | Description |
|---|---|
| `--referral`, `-r` | Referral code to use |
| `--count`, `-n` | Number of accounts to create |

## Output

Output file:

```text
accounts\batch_YYYYMMDD_HHMMSS.txt
```

Example format:

```text
[1] | 26/06/2026
Mail: user@example.com
Link: https://generator.email/user@example.com
Pw: password
Api-Key: sk-...
Balance: $2.72

Total Balance: $2.72

Apikey:
sk-...
```

Only successful accounts with API key are written.

## Notes

- Generated account files are ignored by Git.
- Do not commit `.env`, credentials, or account output files.
- Use `Ctrl+C` to stop a running batch.
