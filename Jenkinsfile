pipeline {
    agent { label 'slave2-node-build' }
    
    environment {
        FRONTEND_IMAGE = "ayush2744/frontend"
        BACKEND_IMAGE  = "ayush2744/backend"
        
    }
    
    stages {
        stage('Checkout') {
            steps {
                git credentialsId: 'jenkins-github',
                    url: 'git@github.com:ayush729874/jenkins-build.git',
                    branch: 'main'
            }
        }
        stage('Get latest Tag') {
            steps {
              script {
                  def latestTag = sh(
                      script: """
                         curl -s "https://hub.docker.com/v2/repositories/ayush2744/frontend/tags/?page_size=100" \
                         | grep -o '"name":"v[0-9]*"' \
                         | grep -o '[0-9]*' \
                         | sort -n \
                         | tail -1
                      """,
                      returnStdout: true
                  ).trim()
                  def nextTag = latestTag ? latestTag.toInteger() + 1 : 1
                  env.IMAGE_TAG = "v${nextTag}"
                  echo "New image tag will be: ${env.IMAGE_TAG}"
                  )
              }
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
