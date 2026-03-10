pipeline {
    agent { label 'slave2-node-build' }

    environment {
        FRONTEND_IMAGE = "ayush2744/frontend"
        BACKEND_IMAGE  = "ayush2744/backend"
        ARGOCD_SERVER  = "argocd.treecom.site:30437"
        ARGOCD_TOKEN   = credentials('argocd-token')
    }

    stages {

        // ─────────────────────────────────────────
        // STAGE 1: Detect which services changed
        // ─────────────────────────────────────────
        stage('Detect Changes') {
            steps {
                script {
                    def changedFiles = sh(
                        script: 'git diff --name-only HEAD~1 HEAD',
                        returnStdout: true
                    ).trim()

                    echo "Changed files:\n${changedFiles}"

                    if (!changedFiles.contains('frontend/') &&
                        !changedFiles.contains('backend/')) {
                        echo "No changes detected in frontend or backend — skipping pipeline."
                        currentBuild.result = 'NOT_BUILT'
                        return
                    }

                    env.BUILD_FRONTEND = changedFiles.contains('frontend/') ? "true" : "false"
                    env.BUILD_BACKEND  = changedFiles.contains('backend/')  ? "true" : "false"
                    env.SHOULD_BUILD   = "true"

                    echo "Build frontend : ${env.BUILD_FRONTEND}"
                    echo "Build backend  : ${env.BUILD_BACKEND}"
                }
            }
        }

        // ─────────────────────────────────────────
        // STAGE 2: Pull latest source code
        // ─────────────────────────────────────────
        stage('Checkout Source') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                git credentialsId: 'jenkins',
                    url: 'git@github.com:ayush729874/jenkins-build.git',
                    branch: 'main'
            }
        }

        // ─────────────────────────────────────────
        // STAGE 3: Determine next image version
        // ─────────────────────────────────────────
        stage('Resolve Image Tag') {
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
                    echo "Next image tag: ${env.IMAGE_TAG}"
                }
            }
        }

        // ─────────────────────────────────────────
        // STAGE 4: Build Docker images
        // ─────────────────────────────────────────
        stage('Build') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                script {
                    if (env.BUILD_FRONTEND == "true") {
                        echo "Building frontend image: ${FRONTEND_IMAGE}:${env.IMAGE_TAG}"
                        sh "docker build -t ${FRONTEND_IMAGE}:${env.IMAGE_TAG} ./frontend"
                    }
                    if (env.BUILD_BACKEND == "true") {
                        echo "Building backend image: ${BACKEND_IMAGE}:${env.IMAGE_TAG}"
                        sh "docker build -t ${BACKEND_IMAGE}:${env.IMAGE_TAG} ./backend"
                    }
                }
            }
        }

        // ─────────────────────────────────────────
        // STAGE 5: Push images to DockerHub registry
        // ─────────────────────────────────────────
        stage('Publish to Registry') {
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

        // ─────────────────────────────────────────
        // STAGE 6: Remove local images after push
        // ─────────────────────────────────────────
        stage('Remove Local Images') {
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

        // ─────────────────────────────────────────
        // STAGE 7: Update test manifest with new tag
        // ─────────────────────────────────────────
        stage('Update Test Manifest') {
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
                        git commit -m "[CI] Update test image tag to ${imageTag}"
                        git push git@github-manifests:ayush729874/k8s_builds.git HEAD:main
                        cd /tmp && rm -rf k8s_builds
                    """
                }
            }
        }

        // ─────────────────────────────────────────
        // STAGE 8: Sync & wait for test deployment
        // ─────────────────────────────────────────
        stage('Deploy to Test') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                withCredentials([string(credentialsId: 'argocd-token', variable: 'ARGOCD_TOKEN')]) {
                    sh '''
                        echo "Triggering ArgoCD sync for test environment..."
                        argocd app sync argocd-app \
                            --server argocd.treecom.site:30437 \
                            --auth-token $ARGOCD_TOKEN \
                            --plaintext \
                            --grpc-web

                        echo "Waiting for test deployment to become healthy..."
                        argocd app wait argocd-app \
                            --health \
                            --sync \
                            --timeout 400 \
                            --server argocd.treecom.site:30437 \
                            --auth-token $ARGOCD_TOKEN \
                            --plaintext \
                            --grpc-web
                    '''
                }
            }
        }

        // ─────────────────────────────────────────
        // STAGE 9: Run automated Selenium tests
        // ─────────────────────────────────────────
        stage('Automated Tests') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                retry(3) {
                    script {
                        def testResult = sh(
                            script: '''
                                cd $WORKSPACE
                                python3 test.py
                            ''',
                            returnStatus: true
                        )
                        if (testResult != 0) {
                            error("Selenium tests failed — production deployment blocked.")
                        }
                    }
                }
                echo "All automated tests passed ✅"
            }
        }

        // ─────────────────────────────────────────
        // STAGE 10: Manual approval gate
        // ─────────────────────────────────────────
        stage('Production Approval') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                script {
                    def message = "✅ Automated tests passed!\n\n"
                    message += "Images ready for production deployment:\n"

                    if (env.BUILD_FRONTEND == "true") {
                        message += "  • Frontend : ayush2744/frontend:${env.IMAGE_TAG}\n"
                    } else {
                        message += "  • Frontend : NO CHANGES (existing image retained)\n"
                    }
                    if (env.BUILD_BACKEND == "true") {
                        message += "  • Backend  : ayush2744/backend:${env.IMAGE_TAG}\n"
                    } else {
                        message += "  • Backend  : NO CHANGES (existing image retained)\n"
                    }

                    message += "\nApprove deployment to Production?"

                    timeout(time: 24, unit: 'HOURS') {
                        input message: message, ok: "Deploy to Production"
                    }
                }
            }
        }

        // ─────────────────────────────────────────
        // STAGE 11: Update prod manifest & deploy
        // ─────────────────────────────────────────
        stage('Deploy to Production') {
            when {
                expression { env.SHOULD_BUILD == "true" }
            }
            steps {
                withCredentials([string(credentialsId: 'argocd-token', variable: 'ARGOCD_TOKEN')]) {
                    script {
                        def imageTag = env.IMAGE_TAG

                        sh '''
                            cd /tmp
                            rm -rf prod_builds
                            git clone git@github-manifests:ayush729874/k8s_builds.git prod_builds
                            cd prod_builds
                            git config user.email "jenkins@ci.com"
                            git config user.name "Jenkins"
                        '''

                        // Always update both services in production
                        // to ensure frontend and backend stay aligned
                        if (env.BUILD_FRONTEND == "true") {
                            sh """
                                cd /tmp/prod_builds
                                sed -i 's|image: ayush2744/frontend:.*|image: ayush2744/frontend:${imageTag}|' prod_builds/deployment.yaml
                            """
                        }
                        if (env.BUILD_BACKEND == "true") {
                            sh """
                                cd /tmp/prod_builds
                                sed -i 's|image: ayush2744/backend:.*|image: ayush2744/backend:${imageTag}|' prod_builds/deployment.yaml
                            """
                        }

                        sh """
                            cd /tmp/prod_builds
                            git add prod_builds/deployment.yaml
                            git commit -m "[CI] Deploy to production: ${imageTag}"
                            git push git@github-manifests:ayush729874/k8s_builds.git HEAD:main
                            cd /tmp && rm -rf prod_builds
                        """

                        sh '''
                            echo "Triggering ArgoCD sync for production environment..."
                            argocd app sync argocd-prod \
                                --server argocd.treecom.site:30437 \
                                --auth-token $ARGOCD_TOKEN \
                                --plaintext \
                                --grpc-web

                            echo "Waiting for production deployment to become healthy..."
                            argocd app wait argocd-prod \
                                --health \
                                --timeout 400 \
                                --server argocd.treecom.site:30437 \
                                --auth-token $ARGOCD_TOKEN \
                                --plaintext \
                                --grpc-web
                        '''

                        echo "✅ Production deployment complete — ${imageTag} is live!"
                    }
                }
            }
        }

    }
}
