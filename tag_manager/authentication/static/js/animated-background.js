document.addEventListener('DOMContentLoaded', function() {
    // Create particles
    const particlesContainer = document.querySelector('.particles');
    const numberOfParticles = 50;

    function createParticle() {
        const particle = document.createElement('div');
        particle.className = 'particle';
        
        // Random starting position
        particle.style.left = Math.random() * 100 + '%';
        particle.style.top = Math.random() * 100 + '%';
        
        // Random size
        const size = Math.random() * 4 + 2;
        particle.style.width = size + 'px';
        particle.style.height = size + 'px';
        
        // Random animation duration
        particle.style.animationDuration = (Math.random() * 4 + 4) + 's';
        
        // Random delay
        particle.style.animationDelay = Math.random() * 2 + 's';
        
        particlesContainer.appendChild(particle);
        
        // Remove particle after animation
        particle.addEventListener('animationend', function() {
            particle.remove();
            createParticle();
        });
    }

    // Create initial particles
    for (let i = 0; i < numberOfParticles; i++) {
        createParticle();
    }
});
