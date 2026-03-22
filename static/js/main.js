document.addEventListener('DOMContentLoaded', () => {
    initLazyLoading();
    initImageModals();
    loadStories();
});

function initLazyLoading() {
    const images = document.querySelectorAll('img[data-src]');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                observer.unobserve(img);
            }
        });
    });
    
    images.forEach(img => observer.observe(img));
}

function initImageModals() {
    document.querySelectorAll('.post-image, .story-image').forEach(img => {
        img.addEventListener('click', () => {
            openImageModal(img.src);
        });
    });
}

function openImageModal(src) {
    const modal = document.createElement('div');
    modal.style.position = 'fixed';
    modal.style.top = '0';
    modal.style.left = '0';
    modal.style.right = '0';
    modal.style.bottom = '0';
    modal.style.background = 'rgba(0,0,0,0.9)';
    modal.style.zIndex = '2000';
    modal.style.display = 'flex';
    modal.style.alignItems = 'center';
    modal.style.justifyContent = 'center';
    modal.style.cursor = 'pointer';
    
    const img = document.createElement('img');
    img.src = src;
    img.style.maxWidth = '90%';
    img.style.maxHeight = '90%';
    img.style.borderRadius = '12px';
    
    modal.appendChild(img);
    modal.onclick = () => modal.remove();
    document.body.appendChild(modal);
}

async function loadStories() {
    try {
        const response = await fetch('/api/stories');
        const stories = await response.json();
        
        const storiesRow = document.getElementById('storiesRow');
        if (!storiesRow) return;
        
        storiesRow.innerHTML = `
            <div class="story-item" onclick="openStoryCamera()">
                <div class="story-ring add-story">
                    <i class="fas fa-plus"></i>
                </div>
                <span>Моя история</span>
            </div>
        `;
        
        stories.forEach(story => {
            const storyEl = document.createElement('div');
            storyEl.className = 'story-item';
            storyEl.onclick = () => viewStory(story);
            storyEl.innerHTML = `
                <div class="story-ring">
                    <img src="${story.media_url}" alt="">
                </div>
                <span>${story.username}</span>
            `;
            storiesRow.appendChild(storyEl);
        });
    } catch (err) {
        console.error('Ошибка загрузки сторис:', err);
    }
}

function viewStory(story) {
    console.log('Просмотр сторис:', story);
    alert('Просмотр сторис в разработке');
}

function openStoryCamera() {
    alert('Скоро появится возможность снимать сторис!');
}