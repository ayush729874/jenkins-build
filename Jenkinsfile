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
        archiveArtifacts artifacts: 'build.txt',
        echo 'Build successful, artifact archived.'
    }
    failure {
        echo 'Build failed.'
    }
        
}
