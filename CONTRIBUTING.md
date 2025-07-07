# 🚀 How to Contribute to Letta

Thank you for investing time in contributing to our project! Here's a guide to get you started.

## 1. 🚀 Getting Started

### 🍴 Fork the Repository

First things first, let's get you a personal copy of Letta to play with. Think of it as your very own playground. 🎪

1. Head over to the Letta repository on GitHub.
2. In the upper-right corner, hit the 'Fork' button.

### 🚀 Clone the Repository

Now, let's bring your new playground to your local machine.

```shell
git clone https://github.com/your-username/letta.git
```

### 🧩 Install dependencies & configure environment

#### Install poetry and dependencies

First, install Poetry using [the official instructions here](https://python-poetry.org/docs/#installation).

Once Poetry is installed, navigate to the letta directory and install the Letta project with Poetry:
```shell
cd letta
eval $(poetry env activate)
poetry install --all-extras
```
#### Setup PostgreSQL environment (optional)

If you are planning to develop letta connected to PostgreSQL database, you need to take the following actions.
If you are not planning to use PostgreSQL database, you can skip to the step which talks about [running letta](#running-letta-with-poetry).

Assuming you have a running PostgreSQL instance, first you need to create the user, database and ensure the pgvector
extension is ready. Here are sample steps for a case where user and database name is letta and assumes no password is set:

```shell
createuser letta
createdb letta --owner=letta
psql -d letta -c 'CREATE EXTENSION IF NOT EXISTS vector'
```
Setup the environment variable to tell letta code to contact PostgreSQL database:
```shell
export LETTA_PG_URI="postgresql://${POSTGRES_USER:-letta}:${POSTGRES_PASSWORD:-letta}@localhost:5432/${POSTGRES_DB:-letta}"
```

After this you need to prep the database with initial content. You can use alembic upgrade to populate the initial
contents from template test data. Please ensure to activate poetry environment using `poetry shell`.
```shell
alembic upgrade head
```

#### Running letta with poetry

Now when you want to use `letta`, make sure you first activate the `poetry` environment using poetry shell:

```shell
$ eval $(poetry env activate)
(letta-py3.12) $ letta run
```

Alternatively, you can use `poetry run` (which will activate the `poetry` environment for the `letta run` command only):
```shell
poetry run letta run
```

#### Installing pre-commit
We recommend installing pre-commit to ensure proper formatting during development:
```
poetry run pre-commit install
poetry run pre-commit run --all-files
```
If you don't install pre-commit, you will need to run `poetry run black .` before submitting a PR.

## 2. 🛠️ Making Changes

### 🌟 Create a Branch

Time to put on your creative hat and make some magic happen. First, let's create a new branch for your awesome changes. 🧙‍♂️

```shell
git checkout -b feature/your-feature
```

### ✏️ Make your Changes

Now, the world is your oyster! Go ahead and craft your fabulous changes. 🎨


#### Handling Database Migrations
If you are running Letta for the first time, your database will be automatically be setup. If you are updating Letta, you may need to run migrations. To run migrations, use the following command:
```shell
poetry run alembic upgrade head
```

#### Creating a new Database Migration
If you have made changes to the database models, you will need to create a new migration. To create a new migration, use the following command:
```shell
poetry run alembic revision --autogenerate -m "Your migration message here"
```

Visit the [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/tutorial.html) for more information on creating and running migrations.

## 3. ✅ Testing

Before we hit the 'Wow, I'm Done' button, let's make sure everything works as expected. Run tests and make sure the existing ones don't throw a fit. And if needed, create new tests. 🕵️

### Setting up API keys for testing

Many tests require API keys for various LLM providers and services. To set these up:

1. Copy the example environment file:
   ```shell
   cp .env.example .env
   ```

2. Edit `.env` and add your API keys. At minimum, you'll need:
   ```shell
   OPENAI_API_KEY=sk-...  # Required for most tests
   ```

3. For comprehensive testing, see `.env.example` for all available API keys and `docs/TESTING_API_KEYS.md` for detailed documentation on obtaining them.

### Run existing tests

Running tests if you installed via poetry:
```
poetry run pytest -s tests
```

Running tests if you installed via pip:
```
pytest -s tests
```

To run tests without certain API keys:
```
# Skip provider-specific tests
poetry run pytest -s tests -m "not anthropic_basic and not gemini_basic"

# Skip sandbox tests requiring E2B
poetry run pytest -s tests -m "not e2b_sandbox"
```

### Creating new tests
If you added a major feature change, please add new tests in the `tests/` directory.

## 4. 🧩 Adding new dependencies
If you need to add a new dependency to Letta, please add the package via `poetry add <PACKAGE_NAME>`. This will update the `pyproject.toml` and `poetry.lock` files. If the dependency does not need to be installed by all users, make sure to mark the dependency as optional in the `pyproject.toml` file and if needed, create a new extra under `[tool.poetry.extras]`.

## 5. 🚀 Submitting Changes

### Check Formatting
Please ensure your code is formatted correctly by running:
```
poetry run black . -l 140
```

### 🚀 Create a Pull Request

You're almost there! It's time to share your brilliance with the world. 🌍

1. Visit [Letta](https://github.com/letta-ai/letta).
2. Click "New Pull Request" button.
3. Choose the base branch (`main`) and the compare branch (your feature branch).
4. Whip up a catchy title and describe your changes in the description. 🪄

## 6. 🔍 Review and Approval

The maintainers will take a look and might suggest some cool upgrades or ask for more details. Once they give the thumbs up, your creation becomes part of Letta!

## 7. 📜 Code of Conduct

Please be sure to follow the project's Code of Conduct.

## 8. 📫 Contact

Need help or just want to say hi? We're here for you. Reach out through filing an issue on this GitHub repository or message us on our [Discord server](https://discord.gg/9GEQrxmVyE).

Thanks for making Letta even more fantastic!

## WIP - 🐋 Docker Development
If you prefer to keep your resources isolated by developing purely in containers, you can start Letta in development with:
```shell
docker compose -f compose.yaml -f development.compose.yml up
```
This will volume mount your local codebase and reload the server on file changes.
