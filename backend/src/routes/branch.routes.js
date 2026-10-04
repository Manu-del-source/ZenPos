const express = require('express');
const router = express.Router();
const branchController = require('../controllers/branch.controller');
const auth = require('../middleware/auth.middleware');
const checkRole = require('../middleware/role.middleware');

router.post('/', auth, checkRole(['ADMIN']), branchController.createBranch);
router.get('/', auth, branchController.getBranches);

module.exports = router;
