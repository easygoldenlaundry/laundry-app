// app/static/js/admin_reviews.js

let allReviews = [];
let filteredReviews = [];

// Load reviews on page load
document.addEventListener('DOMContentLoaded', () => {
    loadReviews();
});

async function loadReviews() {
    try {
        const response = await fetch('/admin/api/reviews');
        if (!response.ok) throw new Error('Failed to load reviews');
        
        const data = await response.json();
        allReviews = data.reviews;
        
        updateStatistics(data.statistics);
        filterReviews();
    } catch (error) {
        console.error('Error loading reviews:', error);
        document.getElementById('reviews-container').innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Failed to load reviews. Please try again.</p>
            </div>
        `;
    }
}

function updateStatistics(stats) {
    document.getElementById('total-reviews').textContent = stats.total_reviews;
    document.getElementById('avg-delivery-rating').textContent = stats.avg_delivery_rating.toFixed(1);
    document.getElementById('avg-quality-rating').textContent = stats.avg_quality_rating.toFixed(1);
    document.getElementById('feedback-count').textContent = stats.feedback_count;
    
    // Generate star ratings
    document.getElementById('delivery-stars').innerHTML = generateStarRating(stats.avg_delivery_rating);
    document.getElementById('quality-stars').innerHTML = generateStarRating(stats.avg_quality_rating);
}

function generateStarRating(rating) {
    const fullStars = Math.floor(rating);
    const hasHalfStar = rating % 1 >= 0.5;
    const emptyStars = 5 - fullStars - (hasHalfStar ? 1 : 0);
    
    let html = '';
    for (let i = 0; i < fullStars; i++) {
        html += '<i class="fas fa-star"></i>';
    }
    if (hasHalfStar) {
        html += '<i class="fas fa-star-half-alt"></i>';
    }
    for (let i = 0; i < emptyStars; i++) {
        html += '<i class="far fa-star"></i>';
    }
    return html;
}

function filterReviews() {
    const ratingFilter = document.getElementById('rating-filter').value;
    const feedbackFilter = document.getElementById('feedback-filter').value;
    const sortBy = document.getElementById('sort-by').value;
    
    // Apply filters
    filteredReviews = allReviews.filter(review => {
        // Rating filter
        if (ratingFilter !== 'all') {
            const avgRating = (review.pickup_delivery_rating + review.laundry_quality_rating) / 2;
            if (ratingFilter === 'low') {
                if (avgRating > 2) return false;
            } else {
                const targetRating = parseInt(ratingFilter);
                if (Math.round(avgRating) !== targetRating) return false;
            }
        }
        
        // Feedback filter
        if (feedbackFilter === 'with' && !review.feedback_text) return false;
        if (feedbackFilter === 'without' && review.feedback_text) return false;
        
        return true;
    });
    
    // Apply sorting
    filteredReviews.sort((a, b) => {
        switch (sortBy) {
            case 'recent':
                return new Date(b.created_at) - new Date(a.created_at);
            case 'oldest':
                return new Date(a.created_at) - new Date(b.created_at);
            case 'highest':
                const avgA = (a.pickup_delivery_rating + a.laundry_quality_rating) / 2;
                const avgB = (b.pickup_delivery_rating + b.laundry_quality_rating) / 2;
                return avgB - avgA;
            case 'lowest':
                const avgA2 = (a.pickup_delivery_rating + a.laundry_quality_rating) / 2;
                const avgB2 = (b.pickup_delivery_rating + b.laundry_quality_rating) / 2;
                return avgA2 - avgB2;
            default:
                return 0;
        }
    });
    
    displayReviews();
}

function displayReviews() {
    const container = document.getElementById('reviews-container');
    
    if (filteredReviews.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <p>No reviews match your filters.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = filteredReviews.map(review => {
        const avgRating = (review.pickup_delivery_rating + review.laundry_quality_rating) / 2;
        const ratingClass = avgRating <= 2 ? 'low-rating' : avgRating >= 4.5 ? 'high-rating' : '';
        const date = new Date(review.created_at).toLocaleString('en-ZA', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
        
        return `
            <div class="review-card ${ratingClass}">
                <div class="review-header">
                    <div class="review-info">
                        <div class="order-id">
                            <i class="fas fa-shopping-bag"></i> Order #${review.order_id}
                        </div>
                        <div class="customer-name">
                            <i class="fas fa-user"></i> ${review.customer_name}
                        </div>
                        ${review.driver_name ? `
                            <div style="margin-top: 0.5rem;">
                                <span class="driver-badge">
                                    <i class="fas fa-truck"></i> Driver: ${review.driver_name}
                                </span>
                            </div>
                        ` : ''}
                    </div>
                    <div class="review-date">
                        <i class="fas fa-clock"></i> ${date}
                    </div>
                </div>
                
                <div class="ratings-grid">
                    <div class="rating-item">
                        <div class="rating-label">
                            <i class="fas fa-truck"></i> Pickup/Delivery:
                        </div>
                        <div class="rating-stars">
                            ${generateStarRating(review.pickup_delivery_rating)}
                        </div>
                        <span class="rating-value">${review.pickup_delivery_rating}/5</span>
                    </div>
                    
                    <div class="rating-item">
                        <div class="rating-label">
                            <i class="fas fa-tshirt"></i> Laundry Quality:
                        </div>
                        <div class="rating-stars">
                            ${generateStarRating(review.laundry_quality_rating)}
                        </div>
                        <span class="rating-value">${review.laundry_quality_rating}/5</span>
                    </div>
                    
                    <div class="rating-item">
                        <div class="rating-label">
                            <i class="fas fa-chart-line"></i> Average:
                        </div>
                        <div class="rating-stars">
                            ${generateStarRating(avgRating)}
                        </div>
                        <span class="rating-value">${avgRating.toFixed(1)}/5</span>
                    </div>
                </div>
                
                ${review.feedback_text ? `
                    <div class="feedback-text">
                        <strong><i class="fas fa-comment"></i> Customer Feedback:</strong>
                        <p style="margin: 0.5rem 0 0 0;">${escapeHtml(review.feedback_text)}</p>
                    </div>
                ` : `
                    <div class="no-feedback">
                        <i class="fas fa-comment-slash"></i> No written feedback provided
                    </div>
                `}
            </div>
        `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function exportReviews() {
    // Create CSV content
    const headers = ['Order ID', 'Customer', 'Driver', 'Pickup/Delivery Rating', 'Quality Rating', 'Average', 'Feedback', 'Date'];
    const rows = filteredReviews.map(review => {
        const avgRating = ((review.pickup_delivery_rating + review.laundry_quality_rating) / 2).toFixed(1);
        const date = new Date(review.created_at).toLocaleDateString('en-ZA');
        return [
            review.order_id,
            `"${review.customer_name}"`,
            `"${review.driver_name || 'N/A'}"`,
            review.pickup_delivery_rating,
            review.laundry_quality_rating,
            avgRating,
            `"${(review.feedback_text || '').replace(/"/g, '""')}"`,
            date
        ];
    });
    
    const csvContent = [
        headers.join(','),
        ...rows.map(row => row.join(','))
    ].join('\n');
    
    // Download CSV
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    
    const timestamp = new Date().toISOString().split('T')[0];
    link.setAttribute('href', url);
    link.setAttribute('download', `reviews_${timestamp}.csv`);
    link.style.visibility = 'hidden';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

