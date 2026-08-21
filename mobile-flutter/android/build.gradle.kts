allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}

// Force all Android subprojects (plugins) to compile against a modern SDK.
// `daily_flutter` 0.31.0 (pulled by `vapi` 0.1.0) hardcodes compileSdk 33, but
// its androidx transitive deps require 34+ (some 36). Lifting every Android
// module to 36 resolves the AAR-metadata mismatch without changing dependency
// versions. compileSdk only affects compile-time API surface — runtime behavior
// is governed by minSdk/targetSdk.
//
// NOTE: this block MUST come before the `evaluationDependsOn(":app")` block
// below — afterEvaluate callbacks must be registered before subprojects are
// force-evaluated, and they must run *after* a plugin's own `android {}` block
// (which is where daily_flutter sets compileSdk 33).
subprojects {
    afterEvaluate {
        if (project.plugins.hasPlugin("com.android.library") ||
            project.plugins.hasPlugin("com.android.application")
        ) {
            project.extensions.configure<com.android.build.gradle.BaseExtension> {
                compileSdkVersion(36)
            }
        }
    }
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
