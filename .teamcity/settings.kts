import jetbrains.buildServer.configs.kotlin.v2019_2.*
import jetbrains.buildServer.configs.kotlin.v2019_2.buildSteps.script
import jetbrains.buildServer.configs.kotlin.v2019_2.triggers.vcs

version = "2021.2"

project {
    description = "TeamCity project for rpg_game - example Kotlin DSL"

    vcsRoot(GitHubRepo)

    buildType(Deploy)
}

object GitHubRepo : GitVcsRoot({
    name = "rpg_game GitHub"
    url = "https://github.com/Ekipogh/rpg_game.git"
    branchSpec = "+:refs/heads/*"
    // authentication should be configured in TeamCity (ssh key or token)
})

object Deploy : BuildType({
    name = "Deploy to same-server agent"

    vcs {
        root(GitHubRepo)
        cleanCheckout = true
    }

    steps {
        script {
            name = "Install dependencies"
            scriptContent = """
            #!/bin/bash
            echo "Installing Python dependencies"
            source .venv/bin/activate
            pip install -r requirements.txt
            """
        }

        script {
            name = "Run migrations"
            scriptContent = """
            #!/bin/bash
            source .venv/bin/activate
            python manage.py migrate --noinput
            """
        }

        script {
            name = "Collect static"
            scriptContent = """
            #!/bin/bash
            source .venv/bin/activate
            python manage.py collectstatic --noinput
            """
        }

        script {
            name = "Restart application service"
            scriptContent = """
            #!/bin/bash
            echo "Restarting rpg_game systemd service"
            sudo systemctl restart rpg_game || true
            sudo systemctl status rpg_game --no-pager
            """
        }
    }

    triggers {
        vcs {
            branchFilter = "+:<default>"
        }
    }

    requirements {
        // Require agent to be on Ubuntu/Linux deployment server
        equals("teamcity.agent.jvm.os.name", "Linux")
    }

    params {
        // Secrets should be stored in TeamCity parameters or vault, not in VCS
        // Example: teamcity.agent.ENV_PROD_DB
    }
})
