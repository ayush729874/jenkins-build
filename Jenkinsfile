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
    success {
        s3Upload(
            profileName: 'jenkins-s3',
            entries: [[
                bucket: 'jenkins.treecom.site',
                sourceFile: '**/target/*.war',
                selectedRegion: 'ap-south-1',
                storageClass: 'STANDARD',
                uploadFromSlave: true,
                useServerSideEncryption: false,
                flatten: false,
                gzipFiles: false,
                managedArtifacts: false,
                noUploadOnFailure: false
            ]],
            consoleLogLevel: 'INFO',
            pluginFailureResultConstraint: 'FAILURE'
        )
    }
}
        
}
