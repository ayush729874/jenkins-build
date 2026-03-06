pipeline {
    agent { label 'slave2-node-build' }
    
    environment {
        FRONTEND_IMAGE = "ayush2744/frontend"
        BACKEND_IMAGE  = "ayush2744/backend"
        IMAGE_TAG      = "v${BUILD_NUMBER}"  // v1, v2, v3 auto increments
    }
    
    stages {
        stage('Checkout') {
            steps {
                git credentialsId: 'jenkins-github',
                    url: 'git@github.com:ayush729874/jenkins-build.git',
                    branch: 'main'
            }
        }
        
        stage('Build Images') {
            steps {
                sh """
                    docker build -t ${FRONTEND_IMAGE}:${IMAGE_TAG} ./frontend
                    docker build -t ${BACKEND_IMAGE}:${IMAGE_TAG} ./backend
                """
            }
        }
        
        stage('Push to DockerHub') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-credentials',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh """
                        echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin
                        docker push ${FRONTEND_IMAGE}:${IMAGE_TAG}
                        docker push ${BACKEND_IMAGE}:${IMAGE_TAG}
                        docker logout
                    """
                }
            }
        }

        stage('Cleanup') {
            steps {
                sh """
                    docker rmi ${FRONTEND_IMAGE}:${IMAGE_TAG}
                    docker rmi ${BACKEND_IMAGE}:${IMAGE_TAG}
                """
            }
        }
    }
}
