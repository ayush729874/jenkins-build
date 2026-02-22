pipeline {
    agent {
        label 'build-node'
    }

    stages {
        stage('Checkout') {
            steps {
                echo 'Checking out source code...'
                // checkout scm
            }
        }

        stage('Build') {
            steps {
                echo 'Building the application...'
                touch build.txt

            }
        }

       
    }

    post {
    success{
        s3Upload consoleLogLevel: 'INFO', dontSetBuildResultOnFailure: false, dontWaitForConcurrentBuildCompletion: false, entries: [[bucket: 'jenkins.treecom.site', excludedFile: '', flatten: false, gzipFiles: false, keepForever: false, managedArtifacts: false, noUploadOnFailure: false, selectedRegion: 'ap-south-1', showDirectlyInBrowser: true, sourceFile: '', storageClass: 'STANDARD', uploadFromSlave: true, useServerSideEncryption: false]], pluginFailureResultConstraint: 'FAILURE', profileName: 'jenkins-s3', userMetadata: []
    }
    }
        
}
