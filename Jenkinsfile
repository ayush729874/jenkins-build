pipeline {
    agent { label 'slave2-node-build' }
    
    environment {
        FRONTEND_IMAGE = "ayush2744/frontend"
        BACKEND_IMAGE  = "ayush2744/backend"
        
    }
    
    stages {
        stage('Check Changes') {
            steps {
                script {
                    def changedFiles = sh(
                        script: 'git diff --name-only HEAD~1 HEAD',
                        returnStdout: true
                    ).trim()
                    
                    echo "Changed files: ${changedFiles}"
                    
                    if (!changedFiles.contains('frontend/') && 
                        !changedFiles.contains('backend/')) {
                        echo "No changes in frontend or backend, skipping build!"
                        currentBuild.result = 'NOT_BUILT'
                        return
                    }
                    env.SHOULD_BUILD = "true"
                }
            }
        }
        stage('Checkout') {
            steps {
                git credentialsId: 'jenkins-github',
                    url: 'git@github.com:ayush729874/jenkins-build.git',
                    branch: 'main'
            }
        }
        stage('Get latest Tag') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
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
                
               }
            }
        }
        stage('Build Images') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                sh """
                    docker build -t ${FRONTEND_IMAGE}:${IMAGE_TAG} ./frontend
                    docker build -t ${BACKEND_IMAGE}:${IMAGE_TAG} ./backend
                """
            }
        }
        
        stage('Push to DockerHub') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
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
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                sh """
                    docker rmi ${FRONTEND_IMAGE}:${IMAGE_TAG}
                    docker rmi ${BACKEND_IMAGE}:${IMAGE_TAG}
                """
            }
        }
        stage('Update Deployment YAML') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                script {
                    sh """
                        git config user.email "jenkins@ci.com"
                        git config user.name "Jenkins"

                        sed -i 's|image: ayush2744/frontend:.*|image: ayush2744/frontend:${env.IMAGE_TAG}|' test_builds/deployment.yaml
                        sed -i 's|image: ayush2744/backend:.*|image: ayush2744/backend:${env.IMAGE_TAG}|' test_builds/deployment.yaml

                        git add test_builds/deployment.yaml
                        git commit -m "Updated image tag to ${env.IMAGE_TAG}"
                        git push git@github.com:ayush729874/jenkins-build.git HEAD:main
                    """
                }
            }
        }
    }

}

