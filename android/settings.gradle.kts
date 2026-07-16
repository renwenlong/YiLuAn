// settings.gradle.kts — YiLuAn Android
// ANDROID-DEV-B0-CORE: 工程骨架 (android-epic-design.md §1§2)
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "YiLuAn"
include(":app")
