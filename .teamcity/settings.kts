import jetbrains.buildServer.configs.kotlin.v2019_2.*
import jetbrains.buildServer.configs.kotlin.v2019_2.buildSteps.script
import jetbrains.buildServer.configs.kotlin.v2019_2.triggers.vcs
import jetbrains.buildServer.configs.kotlin.v2019_2.vcs.GitVcsRoot

version = "2019.2"

project {
    description = "Tested release artifacts and local Ubuntu deployment"
    vcsRoot(GitHubRepo)
    buildType(BuildRelease)
    buildType(Deploy)
}

object GitHubRepo : GitVcsRoot({
    id("GitHubRepo")
    name = "rpg_game GitHub"
    url = "https://github.com/Ekipogh/rpg_game.git"
    branch = "refs/heads/main"
    branchSpec = "+:refs/heads/*"
    // Configure GitHub authentication in TeamCity.
})

object BuildRelease : BuildType({
    id("BuildRelease")
    name = "Build and test release"
    artifactRules = "dist/rpg-game.tar.gz"
    vcs {
        root(GitHubRepo)
        cleanCheckout = true
        branchFilter = "+:<default>"
    }
    steps {
        script {
            name = "Test and package exact revision with offline dependencies"
            scriptContent = """
                #!/bin/bash
                set -euo pipefail
                bash deployment/build-release.sh
            """.trimIndent()
        }
    }
    requirements {
        equals("teamcity.agent.jvm.os.name", "Linux")
        equals("rpg.deploy.target", "local-ubuntu")
    }
})

object Deploy : BuildType({
    id("Deploy")
    name = "Deploy game to local Ubuntu"
    type = BuildTypeSettings.Type.DEPLOYMENT
    maxRunningBuilds = 1
    steps {
        script {
            name = "Install tested release and verify services"
            scriptContent = """
                #!/bin/bash
                set -euo pipefail
                sudo -n /usr/local/sbin/rpg-game-deploy --artifact "%teamcity.build.checkoutDir%/incoming/rpg-game.tar.gz"
            """.trimIndent()
        }
    }
    dependencies {
        snapshot(BuildRelease) {
            onDependencyFailure = FailureAction.FAIL_TO_START
            onDependencyCancel = FailureAction.CANCEL
        }
        artifacts(BuildRelease) {
            buildRule = sameChain()
            artifactRules = "rpg-game.tar.gz => incoming"
            cleanDestination = true
        }
    }
    // Automatic deployment is deliberately disabled until the first supervised run.
    triggers {
        vcs {
            enabled = false
            branchFilter = "+:<default>"
            watchChangesInDependencies = true
        }
    }
    requirements {
        equals("teamcity.agent.jvm.os.name", "Linux")
        equals("rpg.deploy.target", "local-ubuntu")
    }
})
