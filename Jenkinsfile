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

            }
        }

       
    }

    post {
        always {
            echo 'Pipeline finished.'
            cleanWs()
        }
        success {
            echo 'Pipeline succeeded!'
            
        }
        failure {
            echo 'Pipeline failed!'
            
        }
    }
}
