<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

$server = "localhost";
$username = "root";
$password = "";
$dbname = "RecoNest";

$con = mysqli_connect($server, $username, $password, $dbname);

if (!$con) {
    echo "Not connected";
} else {
    echo "Connected<br>";
}

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $name = $_POST['name'] ?? '';
    $email = $_POST['email'] ?? '';
    $password = $_POST['pass'] ?? '';


    $sql = "INSERT INTO `user`(`name`, `email`, `password`) VALUES ('$name','$email','$password')";
    $result = mysqli_query($con, $sql);

    if ($result) {
        echo "Data submitted";
    } else {
        echo "Query failed: " . mysqli_error($con);
    }
}
?>
