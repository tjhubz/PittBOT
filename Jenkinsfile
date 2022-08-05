node {
    def app

    stage('Clone repository') {
        /* Let's make sure we have the repository cloned to our workspace */

        checkout scm
    }

    stage('Build image') {
        /* This builds the actual image; synonymous to
         * docker build on the command line */

        app = docker.build("tjhubz/pittbot")
    }

    if(env.BRANCH_NAME == 'main'){
        stage("push image"){
            docker.withRegistry('https://registry.hub.docker.com', 'docker-hub-credentials') {
                app.push("dev")
            }
        }
    }
    
    if(env.BRANCH_NAME == 'main'){
        stage("push image"){
            docker.withRegistry('https://registry.hub.docker.com', 'docker-hub-credentials') {
                app.push("${env.BUILD_NUMBER}")
                app.push("latest")
            }
        }
    }
}
