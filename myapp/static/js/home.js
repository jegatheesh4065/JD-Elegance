const search = document.getElementById("search");
const products = [
    'Search for "toners"',
    'Search for "lipsticks"',
    'Search for "face wash"',
    'Search for "serums"',
    'Search for "moisturizers"'
];
let i = 0;
setInterval(function () {
    i++;
    if (i >= products.length) {
        i = 0;
    }
    search.placeholder = products[i];
}, 1000);
function openWishlist() {
    document.getElementById("wishlistPanel")
        .classList.add("active");
     document.getElementById("overlay")
        .classList.add("active");
}
function closeWishlist() {
    document.getElementById("wishlistPanel")
        .classList.remove("active");

    document.getElementById("overlay")
        .classList.remove("active");
}
function continueShopping() {
     closeWishlist();
}
function slideLeft() {
    document.getElementById("productContainer").scrollBy({
        left: -500,
        behavior: "smooth"
    });
}

function slideRight() {
    document.getElementById("productContainer").scrollBy({
        left: 500,
        behavior: "smooth"
    });
}


function addWishlist(button, name, price, image) {

    let wishlist = JSON.parse(localStorage.getItem("wishlist")) || [];

    let exists = wishlist.find(function(product) {
        return product.name === name;
    });

    if (!exists) {

        wishlist.push({
            name: name,
            price: price,
            image: image
        });

        localStorage.setItem("wishlist", JSON.stringify(wishlist));

        // Heart change
        button.innerHTML = "♥";
        button.classList.add("liked");

    } else {

        // Already wishlist-la irundha remove
        wishlist = wishlist.filter(function(product) {
            return product.name !== name;
        });

        localStorage.setItem("wishlist", JSON.stringify(wishlist));

        // Heart back to normal
        button.innerHTML = "♡";
        button.classList.remove("liked");
    }

    showWishlist();
    openWishlist();
    updateWishlistCount();
    updateWishlistHearts();
}

/* SHOW WISHLIST */

function showWishlist() {

    let wishlist = JSON.parse(
        localStorage.getItem("wishlist")
    ) || [];

    let content = document.getElementById("wishlistContent");

    if (!content) {
        return;
    }

    content.innerHTML = "";


    if (wishlist.length === 0) {

        content.innerHTML = `
            <div class="empty-wishlist">

                <div class="heart" style="color: #ff2780;font-size: 70px;">♡</div>

                <p>Your wishlist is currently empty</p>

                <p>Add your favourite products here.</p>

                <button
                    class="continue-btn" style="background-color: #ff2780;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    font-weight: bold;
    cursor: pointer;"
                    onclick="continueShopping()">

                    CONTINUE SHOPPING

                </button>

            </div>
        `;

        return;
    }


    wishlist.forEach(function(product, index) {

        content.innerHTML += `

            <div class="wishlist-product">

                <img
                    src="${product.image}"
                    alt="${product.name}"
                >

                <div class="wishlist-product-info">

                    <h4>${product.name}</h4>

                    <p>₹${product.price}</p>

                </div>

                <button
                    class="remove-wishlist"
                    onclick="removeWishlist(${index})">

                    ×

                </button>

            </div>

        `;

    });
}


/* REMOVE */

function removeWishlist(index) {

    let wishlist = JSON.parse(
        localStorage.getItem("wishlist")
    ) || [];

    wishlist.splice(index, 1);

    localStorage.setItem(
        "wishlist",
        JSON.stringify(wishlist)
    );

    showWishlist();
}


/* PAGE LOAD */

document.addEventListener("DOMContentLoaded", function() {

    showWishlist();

});
function updateWishlistCount() {

    let wishlist = JSON.parse(localStorage.getItem("wishlist")) || [];

    document.getElementById("wishlistCount").innerText = wishlist.length;
}

document.addEventListener("DOMContentLoaded", function() {
    showWishlist();
    updateWishlistCount();
    updateWishlistHearts();
});
function updateWishlistHearts() {

    let wishlist = JSON.parse(localStorage.getItem("wishlist")) || [];

    let buttons = document.querySelectorAll(".wishlist-add");

    buttons.forEach(function(button) {

        let productName = button.getAttribute("data-name");

        let exists = wishlist.some(function(product) {
            return product.name === productName;
        });

        if (exists) {
            button.innerHTML = "♥";
            button.classList.add("liked");
        } else {
            button.innerHTML = "♡";
            button.classList.remove("liked");
        }

    });
}