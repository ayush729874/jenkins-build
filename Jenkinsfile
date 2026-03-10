pipeline {
    agent { label 'slave2-node-build' }
    environment {
        FRONTEND_IMAGE = "ayush2744/frontend"
        BACKEND_IMAGE  = "ayush2744/backend"
        ARGOCD_TOKEN   = credentials('argocd-token')
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

                    env.BUILD_FRONTEND = changedFiles.contains('frontend/') ? "true" : "false"
                    env.BUILD_BACKEND  = changedFiles.contains('backend/')  ? "true" : "false"
                    env.SHOULD_BUILD   = "true"

                    echo "Build frontend: ${env.BUILD_FRONTEND}"
                    echo "Build backend: ${env.BUILD_BACKEND}"
                }
            }
        }

        stage('Checkout') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                git credentialsId: 'jenkins',
                    url: 'git@github.com:ayush729874/jenkins-build.git',
                    branch: 'main'
            }
        }

        stage('Get Latest Tag') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                script {
            
                    def repoToCheck = env.BUILD_FRONTEND == "true" ? "frontend" : "backend"

                    def latestTag = sh(
                        script: """
                                 curl -s "https://hub.docker.com/v2/repositories/ayush2744/${repoToCheck}/tags/?page_size=100" \
                                 | grep -o '"name":"v[0-9][0-9]*\\(\\.[0-9]*\\)\\?"' \
                                 | grep -o '[0-9][0-9]*\\(\\.[0-9]*\\)\\?' \
                                 | sort -t. -k1,1n -k2,2n \
                                 | tail -1
                             """,
                             returnStdout: true
                            ).trim()

                            def nextTag
                            if (latestTag) {
                                if (latestTag.contains('.')) {
                                    def parts = latestTag.split('\\.')
                                    def major = parts[0].toInteger()
                                    def minor = parts[1].toInteger()
                                    if (minor >= 9) {
                                        major = major + 1
                                        minor = 0
                                    } else {
                                        minor = minor + 1
                                    }
                                    nextTag = "${major}.${minor}"
                                } else {
                                    nextTag = "${latestTag.toInteger()}.1"
                                }
                            } else {
                                nextTag = "1.0"
                            }
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
                script {
                    if (env.BUILD_FRONTEND == "true") {
                        sh "docker build -t ${FRONTEND_IMAGE}:${env.IMAGE_TAG} ./frontend"
                    }
                    if (env.BUILD_BACKEND == "true") {
                        sh "docker build -t ${BACKEND_IMAGE}:${env.IMAGE_TAG} ./backend"
                    }
                }
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
                    script {
                        sh "echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin"
                        if (env.BUILD_FRONTEND == "true") {
                            sh "docker push ${FRONTEND_IMAGE}:${env.IMAGE_TAG}"
                        }
                        if (env.BUILD_BACKEND == "true") {
                            sh "docker push ${BACKEND_IMAGE}:${env.IMAGE_TAG}"
                        }
                        sh "docker logout"
                    }
                }
            }
        }

        stage('Cleanup') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                script {
                    if (env.BUILD_FRONTEND == "true") {
                        sh "docker rmi ${FRONTEND_IMAGE}:${env.IMAGE_TAG}"
                    }
                    if (env.BUILD_BACKEND == "true") {
                        sh "docker rmi ${BACKEND_IMAGE}:${env.IMAGE_TAG}"
                    }
                }
            }
        }

        stage('Update Deployment YAML') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                script {
                    def imageTag = env.IMAGE_TAG
                    sh '''
                        cd /tmp
                        rm -rf k8s_builds
                        git clone git@github-manifests:ayush729874/k8s_builds.git
                        cd k8s_builds
                        git config user.email "jenkins@ci.com"
                        git config user.name "Jenkins"
                    '''
                    if (env.BUILD_FRONTEND == "true") {
                        sh """
                            cd /tmp/k8s_builds
                            sed -i 's|image: ayush2744/frontend:.*|image: ayush2744/frontend:${imageTag}|' test_builds/deployment.yaml
                        """
                    }
                    if (env.BUILD_BACKEND == "true") {
                        sh """
                            cd /tmp/k8s_builds
                            sed -i 's|image: ayush2744/backend:.*|image: ayush2744/backend:${imageTag}|' test_builds/deployment.yaml
                        """
                    }
                    sh """
                        cd /tmp/k8s_builds
                        git add test_builds/deployment.yaml
                        git commit -m "Updated image tag to ${imageTag}"
                        git push git@github-manifests:ayush729874/k8s_builds.git HEAD:main
                        cd /tmp
                        rm -rf k8s_builds
                    """
                }
            }
        }
        stage('Wait for Test Deploy') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                script {
                    sh """
                        argocd app wait argocd-app \
                            --health \
                            --sync \
                            --timeout 400 \
                            --server argocd.treecom.site:30437 \
                            --auth-token $ARGOCD_TOKEN \
                            --plaintext
                            --grpc-web
                    """
                }
            }
        }
    }
}
