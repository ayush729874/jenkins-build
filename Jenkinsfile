pipeline {
    agent {
        label 'build-node'
    }

    stages {
        stage('Checkout') {
            steps {
                echo 'Checking out source code...'
            }
        }

        stage('Build') {
            steps {
                echo 'Building the application...'
                sh 'touch build.txt'
            }
        }
    }

    post {
        success {
            archiveArtifacts artifacts: 'build.txt'
            echo 'Build successful, artifact archived.'
        }
        failure {
            echo 'Build failed.'
        }
    }
}