# Simple Flask Calculator API

A basic Flask application with calculator and user management functionality.

## Features

- **Calculator Operations**: add, subtract, multiply, divide
- **User Management**: create, get, list, delete users
- **Calculation History**: track all calculations

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Welcome message |
| GET | `/health` | Health check |
| POST | `/calculate` | Perform calculation |
| GET | `/users` | List all users |
| POST | `/users` | Create a user |
| GET | `/users/<username>` | Get a user |
| DELETE | `/users/<username>` | Delete a user |
| GET | `/history` | Get calculation history |

## Usage

```bash
pip install -r requirements.txt
python app.py
```

## Example Requests

### Calculate
```bash
curl -X POST http://localhost:5000/calculate \
  -H "Content-Type: application/json" \
  -d '{"operation": "add", "a": 5, "b": 3}'
```

### Create User
```bash
curl -X POST http://localhost:5000/users \
  -H "Content-Type: application/json" \
  -d '{"username": "john", "email": "john@example.com"}'
```
